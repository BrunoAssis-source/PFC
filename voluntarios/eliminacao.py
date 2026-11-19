from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from estudos.models import Estudo

from .models import DecisaoCandidato, Participacao, RegistroAnonimo, ValorColetado, ValorSensivel, Voluntario

Situacao = Participacao.Situacao

# Participação que vincula o voluntário ao estudo, mais a decisão do RF12 (incluído ou recusado).
SITUACOES_QUE_VINCULAM = (Situacao.EM_COLETA, Situacao.CONCLUIDA, Situacao.ELIMINADA)


def com_outro_estudo_ativo(estudo):
    """Condição sobre Voluntario: tem vínculo com algum estudo ativo que não seja o informado.

    É a regra única do RF12 (recusa) e do RF13 (encerramento). Compara por conjuntos no banco, sem iterar voluntários.
    """
    participacoes = (
        Participacao.objects.filter(estudo__situacao=Estudo.Situacao.ATIVO, situacao__in=SITUACOES_QUE_VINCULAM)
        .exclude(estudo=estudo)
        .values("voluntario_id")
    )
    decisoes = (
        DecisaoCandidato.objects.filter(estudo__situacao=Estudo.Situacao.ATIVO)
        .exclude(estudo=estudo)
        .values("codigo_voluntario")
    )
    return Q(id__in=participacoes) | Q(codigo_hmac__in=decisoes)


def tem_outro_estudo_ativo(voluntario, estudo):
    return Voluntario.objects.filter(pk=voluntario.pk).filter(com_outro_estudo_ativo(estudo)).exists()


def apagar_dados(voluntarios):
    """Apaga CPF, código, valores comuns e sensíveis e participações dos voluntários informados."""
    ids = [v.id for v in voluntarios]
    codigos = [v.codigo_hmac for v in voluntarios]
    ValorColetado.objects.filter(codigo_voluntario__in=codigos).delete()
    ValorSensivel.objects.filter(codigo_voluntario__in=codigos).delete()
    Participacao.objects.filter(voluntario_id__in=ids).delete()
    Voluntario.objects.filter(id__in=ids).delete()


def _vinculados(estudo):
    por_participacao = Participacao.objects.filter(estudo=estudo, situacao__in=SITUACOES_QUE_VINCULAM)
    por_decisao = DecisaoCandidato.objects.filter(estudo=estudo)
    return Voluntario.objects.filter(
        Q(id__in=por_participacao.values("voluntario_id")) | Q(codigo_hmac__in=por_decisao.values("codigo_voluntario"))
    )


def separar(estudo):
    """Voluntários vinculados ao estudo, divididos entre os que perdem os dados e os que ficam por outro estudo ativo."""
    vinculados = _vinculados(estudo)
    return vinculados.exclude(com_outro_estudo_ativo(estudo)), vinculados.filter(com_outro_estudo_ativo(estudo))


def previa(estudo):
    eliminar, manter = separar(estudo)
    return {"eliminados": eliminar.count(), "mantidos": manter.count()}


def previa_da_conta(usuario):
    previas = [previa(estudo) for estudo in usuario.estudos.all()]
    return {
        "estudos": len(previas),
        "eliminados": sum(p["eliminados"] for p in previas),
        "mantidos": sum(p["mantidos"] for p in previas),
    }


def _guardar_so_a_contagem(voluntarios):
    # Copia o que o painel conta antes de a participação sumir, sem código nem ligação com o voluntário.
    incluidos = set(
        DecisaoCandidato.objects.filter(
            codigo_voluntario__in=[v.codigo_hmac for v in voluntarios], decisao=DecisaoCandidato.Decisao.INCLUIDO
        ).values_list("estudo_id", "codigo_voluntario")
    )
    RegistroAnonimo.objects.bulk_create(
        RegistroAnonimo(
            estudo_id=p.estudo_id,
            situacao=p.situacao,
            incluido=(p.estudo_id, p.voluntario.codigo_hmac) in incluidos,
            criterio_reprovado_id=p.criterio_reprovado_id,
            entrou_em=p.tcle_aceito_em,
        )
        for p in Participacao.objects.filter(voluntario__in=voluntarios).select_related("voluntario")
    )
    DecisaoCandidato.objects.filter(codigo_voluntario__in=[v.codigo_hmac for v in voluntarios]).delete()


@transaction.atomic
def encerrar(estudo, usuario, request=None):
    """RF13: encerra o estudo e elimina quem não tem outro estudo ativo, tudo na mesma transação.

    Qualquer falha desfaz o conjunto, então o estudo mantém a situação anterior e nenhum dado é apagado.
    """
    estudo = Estudo.objects.select_for_update().get(pk=estudo.pk)
    if estudo.situacao == Estudo.Situacao.ENCERRADO:
        raise PermissionDenied("Estudo encerrado não volta a ficar ativo e não é encerrado de novo.")
    estudo.situacao = Estudo.Situacao.ENCERRADO
    estudo.save(update_fields=["situacao"])

    eliminar, manter = separar(estudo)
    voluntarios = list(eliminar.only("id", "codigo_hmac"))
    mantidos = manter.count()
    if voluntarios:
        _guardar_so_a_contagem(voluntarios)
        apagar_dados(voluntarios)

    # Só o estudo e as quantidades. O código curto de auditorias antigas perde a ligação com qualquer pessoa.
    registrar(
        RegistroAuditoria.Acao.ELIMINACAO_ENCERRAMENTO,
        request=request,
        usuario=usuario,
        objeto=f"{estudo.nome}. Eliminados: {len(voluntarios)}. Mantidos por outro estudo ativo: {mantidos}",
    )
    return {"eliminados": len(voluntarios), "mantidos": mantidos}


@transaction.atomic
def excluir(estudo, usuario, request=None):
    """Exclui o estudo e elimina quem não tem outro estudo ativo, com a mesma regra do encerramento.

    Quem permanece por outro estudo ativo perde só a participação neste estudo. Os valores continuam com o
    voluntário, sem a participação que os coletou.
    """
    estudo = Estudo.objects.select_for_update().get(pk=estudo.pk)
    eliminar, manter = separar(estudo)
    voluntarios = list(eliminar.only("id", "codigo_hmac"))
    mantidos = manter.count()
    if voluntarios:
        DecisaoCandidato.objects.filter(codigo_voluntario__in=[v.codigo_hmac for v in voluntarios]).delete()
        apagar_dados(voluntarios)

    # Sobram as participações dos mantidos e as interrompidas ou revogadas, que a PROTECT impediria de seguir.
    Participacao.objects.filter(estudo=estudo).delete()
    estudo.decisoes.all().delete()
    estudo.registros_anonimos.all().delete()
    nome = estudo.nome
    estudo.delete()

    registrar(
        RegistroAuditoria.Acao.ELIMINACAO_EXCLUSAO,
        request=request,
        usuario=usuario,
        objeto=f"{nome}. Eliminados: {len(voluntarios)}. Mantidos por outro estudo ativo: {mantidos}",
    )
    return {"eliminados": len(voluntarios), "mantidos": mantidos}
