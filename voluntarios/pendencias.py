from django.db import connection

from catalogo.models import Variavel
from estudos.models import Estudo

from .email import enviar
from .models import PendenciaNotificada, Voluntario


def _consultar(sql, parametros=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parametros)
        return cursor.fetchall()


def classificacao(voluntario_id=None, estudo_id=None):
    """RN26 pela view voluntarios_classificacao. Devolve {(voluntario_id, estudo_id): classe} dos estudos ativos."""
    linhas = _consultar(
        "SELECT voluntario_id, estudo_id, classe FROM voluntarios_classificacao "
        "WHERE (%s IS NULL OR voluntario_id = %s) AND (%s IS NULL OR estudo_id = %s)",
        [voluntario_id, voluntario_id, estudo_id, estudo_id],
    )
    return {(voluntario, estudo): classe for voluntario, estudo, classe in linhas}


def variaveis_faltantes(voluntario_id, estudo_id):
    """Variáveis sem valor válido que impedem avaliar todos os critérios do estudo, na ordem em que se perguntam."""
    ids = [
        linha[0]
        for linha in _consultar(
            "SELECT variavel_id FROM voluntarios_faltantes WHERE voluntario_id = %s AND estudo_id = %s",
            [voluntario_id, estudo_id],
        )
    ]
    # Sensíveis por último, para quem seria eliminado não responder pergunta sensível à toa.
    return sorted(Variavel.objects.filter(id__in=ids), key=lambda v: (v.sensivel, v.subcategoria_id, v.codigo))


def pendentes(estudo_id=None, voluntario_id=None):
    """Pares pendentes de voluntários que já têm dados na base, com só as variáveis que faltam coletar.

    Não carrega critério, valor nem classificação: a tela do profissional não os mostra (RN25 e RN28).
    """
    pares = _consultar(
        "SELECT voluntario_id, estudo_id FROM voluntarios_classificacao "
        "WHERE classe = 'pendente' AND registrado "
        "AND (%s IS NULL OR estudo_id = %s) AND (%s IS NULL OR voluntario_id = %s) "
        "ORDER BY estudo_id, voluntario_id",
        [estudo_id, estudo_id, voluntario_id, voluntario_id],
    )
    voluntarios = Voluntario.objects.in_bulk({v for v, _ in pares})
    estudos = Estudo.objects.in_bulk({e for _, e in pares})
    return [
        {
            "voluntario": voluntarios[v],
            "estudo": estudos[e],
            "codigo": voluntarios[v].codigo_hmac[:8],
            "variaveis": variaveis_faltantes(v, e),
        }
        for v, e in pares
    ]


def sincronizar_notificacoes(estudo=None, voluntario=None):
    """RN29: avisa o profissional quando surge uma pendência nova, uma vez por pendência.

    Compara as pendências de agora com as já avisadas. As que deixaram de ser pendentes saem do registro, para um
    novo vencimento avisar de novo. O aviso vai ao profissional que cadastrou o voluntário e leva só o estudo e os
    códigos curtos, sem CPF, valores nem critérios.
    """
    atuais = pendentes(estudo.id if estudo else None, voluntario.id if voluntario else None)
    chaves = {(linha["voluntario"].id, linha["estudo"].id) for linha in atuais}

    avisadas = PendenciaNotificada.objects.all()
    if estudo:
        avisadas = avisadas.filter(estudo=estudo)
    if voluntario:
        avisadas = avisadas.filter(voluntario=voluntario)
    ja_avisadas = {(n.voluntario_id, n.estudo_id) for n in avisadas}
    avisadas.exclude(pk__in=[n.pk for n in avisadas if (n.voluntario_id, n.estudo_id) in chaves]).delete()

    novas = [linha for linha in atuais if (linha["voluntario"].id, linha["estudo"].id) not in ja_avisadas]
    PendenciaNotificada.objects.bulk_create(
        [PendenciaNotificada(voluntario=linha["voluntario"], estudo=linha["estudo"]) for linha in novas]
    )

    por_destino = {}
    for linha in novas:
        profissional = linha["voluntario"].criado_por
        if profissional.is_active:
            por_destino.setdefault((profissional, linha["estudo"]), []).append(linha["codigo"])
    for (profissional, estudo_da_pendencia), codigos in por_destino.items():
        enviar(
            profissional.email,
            f"Nova pendência de coleta no estudo {estudo_da_pendencia.nome}",
            "voluntarios/pendencia_email.txt",
            {"profissional": profissional, "estudo": estudo_da_pendencia, "codigos": ", ".join(sorted(codigos))},
            "nova pendência ao profissional",
        )
