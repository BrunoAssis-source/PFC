from django.db import connection

from catalogo.models import Variavel
from estudos.models import Criterio, Estudo

from .email import enviar
from .models import Participacao, PendenciaNotificada, ValorColetado, ValorSensivel, Voluntario


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


POR_PAGINA = 25
SITUACOES = ("inelegivel", "pendente", "em_coleta", "elegivel")

# Filtra no banco quem a tela lista. Fica de fora quem nunca participou deste estudo e não tem valor algum na base,
# porque a view cruza todo voluntário com todo estudo ativo e ele apareceria como pendente em todos, e quem foi
# eliminado na coleta, que a tela do estudo já lista. Quem está em coleta neste estudo e ainda tem falta aparece como
# em_coleta, senão o voluntário recém-cadastrado pareceria pendente.
BASE_DA_TELA = """
WITH base AS (
    SELECT c.voluntario_id, v.codigo_hmac, (p.id IS NOT NULL) AS deste,
           CASE WHEN c.classe = 'pendente' AND p.situacao = 'em_coleta' THEN 'em_coleta' ELSE c.classe END AS classe
    FROM voluntarios_classificacao c
    JOIN voluntarios_voluntario v ON v.id = c.voluntario_id
    LEFT JOIN voluntarios_participacao p ON p.voluntario_id = c.voluntario_id AND p.estudo_id = c.estudo_id
    WHERE c.estudo_id = %s
      AND (c.registrado OR p.id IS NOT NULL)
      AND COALESCE(p.situacao, '') <> 'eliminada'
      AND (%s = '' OR (p.id IS NOT NULL) = (%s = 'deste'))
)
"""


def classificacao_do_estudo(estudo, origem="", pagina=1, por_pagina=POR_PAGINA):
    """Uma página da tela de classificação do pesquisador, com a contagem por situação.

    A contagem e a página saem do banco, então o custo de memória é o de uma página, e os critérios reprovados e as
    variáveis faltantes são buscados só para os voluntários dela. Origem "deste" mantém quem tem participação neste
    estudo e "outros" quem chegou pelos dados registrados em outro estudo.
    """
    filtro = [estudo.id, origem, origem]
    totais = dict(_consultar(BASE_DA_TELA + "SELECT classe, count(*) FROM base GROUP BY classe", filtro))
    paginas = max(1, -(-sum(totais.values()) // por_pagina))
    pagina = min(max(pagina, 1), paginas)
    pagina_do_banco = _consultar(
        BASE_DA_TELA
        + "SELECT voluntario_id, codigo_hmac, deste, classe FROM base "
        "ORDER BY array_position(%s::text[], classe), codigo_hmac LIMIT %s OFFSET %s",
        filtro + [list(SITUACOES), por_pagina, (pagina - 1) * por_pagina],
    )
    resultado = {"linhas": [], "totais": {s: totais.get(s, 0) for s in SITUACOES}, "pagina": pagina, "paginas": paginas}
    if not pagina_do_banco:
        return resultado

    ids = [v for v, *_ in pagina_do_banco]
    reprovados = {}
    for voluntario, criterio in _consultar(
        "SELECT voluntario_id, criterio_id FROM voluntarios_avaliacao_par "
        "WHERE estudo_id = %s AND voluntario_id = ANY(%s) AND NOT cumpre",
        [estudo.id, ids],
    ):
        reprovados.setdefault(voluntario, set()).add(criterio)

    faltantes = {}
    for voluntario, variavel in _consultar(
        "SELECT voluntario_id, variavel_id FROM voluntarios_faltantes WHERE estudo_id = %s AND voluntario_id = ANY(%s)",
        [estudo.id, ids],
    ):
        faltantes.setdefault(voluntario, []).append(variavel)

    criterios = Criterio.objects.select_related("variavel").prefetch_related("opcoes").in_bulk(
        {c for ids_do_voluntario in reprovados.values() for c in ids_do_voluntario}
    )
    variaveis = Variavel.objects.in_bulk({x for ids_do_voluntario in faltantes.values() for x in ids_do_voluntario})

    # A view de faltantes já trata o valor fora da vida útil como ausente. Aqui só se separa quem nunca respondeu
    # de quem tem resposta vencida, para o pesquisador saber que a segunda precisa ser atualizada.
    respondidas = set()
    for modelo in (ValorColetado, ValorSensivel):
        respondidas.update(
            modelo.objects.filter(
                codigo_voluntario__in=[codigo for _, codigo, *_ in pagina_do_banco], variavel_id__in=variaveis
            ).values_list("codigo_voluntario", "variavel_id")
        )

    def motivo(voluntario):
        regras = [criterios[c] for c in sorted(reprovados.get(voluntario, ())) if c in criterios]
        nao_atende = [c.descricao for c in regras if c.tipo_regra == Criterio.TipoRegra.INCLUSAO]
        excluido_por = [c.descricao for c in regras if c.tipo_regra == Criterio.TipoRegra.EXCLUSAO]
        partes = []
        if nao_atende:
            partes.append("Não atende: " + "; ".join(nao_atende))
        if excluido_por:
            partes.append("Atende à exclusão: " + "; ".join(excluido_por))
        return ". ".join(partes)

    def faltam(voluntario, codigo):
        ordenadas = sorted(
            (variaveis[x] for x in faltantes.get(voluntario, [])), key=lambda f: (f.sensivel, f.subcategoria_id, f.codigo)
        )
        return [f"{f.rotulo} (vencida)" if (codigo, f.id) in respondidas else f.rotulo for f in ordenadas]

    resultado["linhas"] = [
        {
            "codigo": codigo[:8],
            "classe": classe,
            "deste_estudo": deste,
            "motivo": motivo(voluntario),
            "faltam": faltam(voluntario, codigo),
        }
        for voluntario, codigo, deste, classe in pagina_do_banco
    ]
    return resultado
