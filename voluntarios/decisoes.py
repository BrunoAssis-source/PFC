import re

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from estudos.models import Estudo

from .models import DecisaoCandidato, Participacao, ValorColetado, ValorSensivel, Voluntario
from .pendencias import _consultar, classificacao

Decisao = DecisaoCandidato.Decisao
Acao = RegistroAuditoria.Acao

POR_PAGINA = 25
SITUACOES = ("elegivel", "pendente", "em_coleta", "inelegivel")
MOTIVOS = {
    "pendente": "pendente, a coleta precisa ser concluída antes da inclusão",
    "inelegivel": "inelegível pelos critérios do estudo",
}

# Mesma base da tela de classificação, com a decisão ao lado. Origem "deste" é quem tem participação coletada neste
# estudo. Quem entrou por inclusão com dados de outro estudo tem participação reaproveitada e conta como "outros".
BASE = """
WITH base AS (
    SELECT c.voluntario_id, v.codigo_hmac, d.decisao,
           (p.id IS NOT NULL AND p.origem = 'coletado') AS deste,
           CASE WHEN c.classe = 'pendente' AND p.situacao = 'em_coleta' THEN 'em_coleta' ELSE c.classe END AS classe
    FROM voluntarios_classificacao c
    JOIN voluntarios_voluntario v ON v.id = c.voluntario_id
    LEFT JOIN voluntarios_participacao p ON p.voluntario_id = c.voluntario_id AND p.estudo_id = c.estudo_id
    LEFT JOIN voluntarios_decisaocandidato d ON d.estudo_id = c.estudo_id AND d.codigo_voluntario = v.codigo_hmac
    WHERE c.estudo_id = %s
      AND (c.registrado OR p.id IS NOT NULL)
      AND COALESCE(p.situacao, '') <> 'eliminada'
)
SELECT * FROM base
WHERE (%s = '' OR deste = (%s = 'deste'))
  AND (%s = '' OR COALESCE(decisao, 'sem') = %s)
  AND codigo_hmac LIKE %s
  AND classe = ANY(%s::text[])
"""


def meta(estudo):
    """Passar da meta é só um aviso, a inclusão não é barrada."""
    incluidos = estudo.decisoes.filter(decisao=Decisao.INCLUIDO).count()
    necessarios = estudo.participantes_necessarios
    return {"incluidos": incluidos, "necessarios": necessarios, "acima": necessarios is not None and incluidos > necessarios}


def candidatos(estudo, situacoes=("elegivel",), origem="", decisao="", codigo="", pagina=1, por_pagina=POR_PAGINA):
    """Uma página de candidatos do estudo, só com o código curto. Nunca lê nem devolve o CPF.

    Mostra só as situações pedidas, por padrão os elegíveis. Quem já foi incluído e mudou de situação só aparece se a
    situação atual dele estiver entre as pedidas.
    Estudo que não está ativo não tem classificação, então devolve só as decisões já registradas.
    """
    resultado = {"linhas": [], "pagina": 1, "paginas": 1, "total": 0, "meta": meta(estudo)}
    if estudo.situacao != Estudo.Situacao.ATIVO:
        decisoes = estudo.decisoes.order_by("codigo_voluntario")
        if decisao in Decisao.values:
            decisoes = decisoes.filter(decisao=decisao)
        total = decisoes.count()
        resultado.update(total=total, paginas=max(1, -(-total // por_pagina)))
        resultado["pagina"] = min(max(pagina, 1), resultado["paginas"])
        inicio = (resultado["pagina"] - 1) * por_pagina
        resultado["linhas"] = [
            {"codigo": d.codigo_voluntario[:8], "decisao": d.decisao, "classe": d.classificacao_na_decisao, "decidido_em": d.decidido_em}
            for d in decisoes[inicio : inicio + por_pagina]
        ]
        return resultado

    # O código só tem hexadecimal minúsculo. Outro caractere não casa com ninguém, e % e _ não viram curinga.
    prefixo = codigo.strip().lower()
    padrao = (prefixo if re.fullmatch("[0-9a-f]*", prefixo) else "!") + "%"
    filtro = [
        estudo.id, origem, origem, decisao, decisao, padrao, list(situacoes) or ["elegivel"],
    ]
    total = _consultar(f"SELECT count(*) FROM ({BASE}) t", filtro)[0][0]
    paginas = max(1, -(-total // por_pagina))
    pagina = min(max(pagina, 1), paginas)
    linhas = _consultar(
        f"SELECT voluntario_id, codigo_hmac, classe, deste, decisao FROM ({BASE}) t "
        "ORDER BY array_position(%s::text[], classe), codigo_hmac LIMIT %s OFFSET %s",
        filtro + [list(SITUACOES), por_pagina, (pagina - 1) * por_pagina],
    )
    resultado.update(
        total=total, pagina=pagina, paginas=paginas,
        linhas=[
            {
                "voluntario_id": voluntario_id,
                "codigo": codigo_hmac[:8],
                "classe": classe_atual,
                "origem": "deste" if deste else "outros",
                "decisao": decisao_gravada,
                # A decisão não muda sozinha. Quem deixou de ser elegível segue incluído, com este aviso.
                "mudou_desde_a_inclusao": decisao_gravada == Decisao.INCLUIDO and classe_atual != "elegivel",
            }
            for voluntario_id, codigo_hmac, classe_atual, deste, decisao_gravada in linhas
        ],
    )
    return resultado


def incluir(estudo, voluntario_ids, usuario, request=None):
    """RN31: só entra quem ainda é elegível agora. Os demais voltam no relatório com o motivo."""
    return _decidir(estudo, voluntario_ids, usuario, Decisao.INCLUIDO, request)


def recusar(estudo, voluntario_ids, usuario, request=None):
    """A recusa é livre, para qualquer situação. Recusar quem estava incluído desfaz o vínculo."""
    return _decidir(estudo, voluntario_ids, usuario, Decisao.RECUSADO, request)


def _decidir(estudo, voluntario_ids, usuario, nova, request):
    with transaction.atomic():
        # A trava no estudo serializa lotes simultâneos. Sem ela, duas inclusões do mesmo voluntário se cruzariam
        # entre a conferência da classificação e a gravação.
        estudo = Estudo.objects.select_for_update().get(pk=estudo.pk)
        if estudo.situacao != Estudo.Situacao.ATIVO:
            raise PermissionDenied("Só o estudo ativo aceita decisão sobre candidatos.")
        ids = list(dict.fromkeys(voluntario_ids))
        voluntarios = Voluntario.objects.in_bulk(ids)
        relatorio = {"feitos": [], "pulados": []}
        # Sem critérios a view classifica todos como elegíveis, e isso não é uma avaliação.
        sem_criterios = not estudo.criterios.exists()
        for voluntario_id in ids:
            voluntario = voluntarios.get(voluntario_id)
            if voluntario is None:
                relatorio["pulados"].append(("", "voluntário não encontrado"))
                continue
            codigo = voluntario.codigo_hmac[:8]
            anterior = DecisaoCandidato.objects.filter(estudo=estudo, codigo_voluntario=voluntario.codigo_hmac).first()
            if anterior and anterior.decisao == nova:
                relatorio["pulados"].append((codigo, f"já estava {Decisao(nova).label}"))
                continue
            classe = classificacao(voluntario.id, estudo.id).get((voluntario.id, estudo.id), "")
            if nova == Decisao.INCLUIDO and (sem_criterios or classe != "elegivel"):
                motivo = "o estudo não tem critérios" if sem_criterios else MOTIVOS.get(classe, "fora da classificação do estudo")
                relatorio["pulados"].append((codigo, motivo))
                continue

            DecisaoCandidato.objects.update_or_create(
                estudo=estudo,
                codigo_voluntario=voluntario.codigo_hmac,
                defaults={
                    "decisao": nova, "decidido_por": usuario, "decidido_em": timezone.now(),
                    "classificacao_na_decisao": classe,
                },
            )
            apagou = False
            if nova == Decisao.INCLUIDO:
                _vincular(estudo, voluntario, usuario)
            elif anterior:
                apagou = _desfazer_vinculo(estudo, voluntario)
            _auditar(request, usuario, estudo, codigo, anterior, nova, apagou)
            relatorio["feitos"].append(codigo)
        relatorio["meta"] = meta(estudo)
    return relatorio


def _vincular(estudo, voluntario, usuario):
    # Quem já participou do estudo mantém a participação. Quem vem de outro estudo ganha uma reaproveitada, sem TCLE.
    Participacao.objects.get_or_create(
        voluntario=voluntario,
        estudo=estudo,
        defaults={
            "tcle_versao": "", "registrado_por": usuario, "origem": Participacao.Origem.REAPROVEITADO,
            "situacao": Participacao.Situacao.CONCLUIDA, "encerrada_em": timezone.now(),
        },
    )


def _desfazer_vinculo(estudo, voluntario):
    """Devolve se os dados do voluntário foram apagados por ele não ter mais estudo ativo vinculado."""
    # A participação coletada neste estudo fica, porque os valores guardam a origem por ela.
    Participacao.objects.filter(voluntario=voluntario, estudo=estudo, origem=Participacao.Origem.REAPROVEITADO).delete()
    outro_estudo = (
        Participacao.objects.filter(
            voluntario=voluntario,
            estudo__situacao=Estudo.Situacao.ATIVO,
            situacao__in=[Participacao.Situacao.EM_COLETA, Participacao.Situacao.CONCLUIDA],
        )
        .exclude(estudo=estudo)
        .exists()
    )
    if outro_estudo:
        return False
    ValorColetado.objects.filter(codigo_voluntario=voluntario.codigo_hmac).delete()
    ValorSensivel.objects.filter(codigo_voluntario=voluntario.codigo_hmac).delete()
    voluntario.participacoes.all().delete()
    voluntario.delete()
    return True


def _auditar(request, usuario, estudo, codigo, anterior, nova, apagou):
    # Só o código curto e o nome do estudo, nunca CPF nem valor coletado.
    objeto = f"{codigo} em {estudo.nome}"
    if anterior:
        acao = Acao.DECISAO_ALTERACAO
        objeto += f". Antes: {anterior.decisao}. Depois: {nova}"
        if apagou:
            objeto += ". Dados do voluntário apagados"
    else:
        acao = Acao.DECISAO_INCLUSAO if nova == Decisao.INCLUIDO else Acao.DECISAO_RECUSA
    registrar(acao, request=request, usuario=usuario, objeto=objeto)
