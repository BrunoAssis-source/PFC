from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.utils import timezone

from voluntarios.models import Participacao, RegistroAnonimo

from .models import Criterio, Estudo

SEMANAS = 8


def eliminacoes(pesquisador):
    """Único ponto que lê as eliminações do painel, para a mudança na forma de registrá-las ficar só aqui.

    A eliminação é a participação na situação eliminada, com o critério reprovado guardado nela. Depois que o estudo
    encerra, as participações somem e a contagem passa a vir dos registros anônimos.
    """
    agrupadas = []
    por_estudo = {}
    for modelo in (Participacao, RegistroAnonimo):
        base = modelo.objects.filter(estudo__pesquisador=pesquisador, situacao=Participacao.Situacao.ELIMINADA)
        for estudo_id, total in base.values_list("estudo_id").annotate(total=Count("id")):
            por_estudo[estudo_id] = por_estudo.get(estudo_id, 0) + total
        agrupadas += base.values("estudo_id", "criterio_reprovado_id").annotate(total=Count("id"))
    somadas = {}
    for linha in agrupadas:
        chave = (linha["estudo_id"], linha["criterio_reprovado_id"])
        somadas[chave] = somadas.get(chave, 0) + linha["total"]
    agrupadas = sorted(
        ({"estudo_id": e, "criterio_reprovado_id": c, "total": t} for (e, c), t in somadas.items()),
        key=lambda linha: -linha["total"],
    )
    criterios = Criterio.objects.select_related("variavel").prefetch_related("opcoes").in_bulk(
        {linha["criterio_reprovado_id"] for linha in agrupadas if linha["criterio_reprovado_id"]}
    )
    por_criterio = {}
    for linha in agrupadas:
        criterio = criterios.get(linha["criterio_reprovado_id"])
        frase = criterio.frase if criterio else "Critério removido do estudo"
        por_criterio.setdefault(linha["estudo_id"], []).append({"frase": frase, "total": linha["total"]})
    return {"total": sum(por_estudo.values()), "por_estudo": por_estudo, "por_criterio": por_criterio}


def _percentual(parte, todo):
    return round(100 * parte / todo) if todo else 0


def _estudos(pesquisador, eliminadas):
    estudos = Estudo.objects.filter(pesquisador=pesquisador).annotate(
        concluidos=Count("participacoes", filter=Q(participacoes__situacao=Participacao.Situacao.CONCLUIDA)),
        em_coleta=Count("participacoes", filter=Q(participacoes__situacao=Participacao.Situacao.EM_COLETA)),
    )
    anonimos_concluidos = dict(
        RegistroAnonimo.objects.filter(estudo__pesquisador=pesquisador, situacao=Participacao.Situacao.CONCLUIDA)
        .values_list("estudo_id")
        .annotate(total=Count("id"))
    )
    linhas = []
    for estudo in estudos.order_by("nome"):
        estudo.concluidos += anonimos_concluidos.get(estudo.id, 0)
        eliminados = eliminadas["por_estudo"].get(estudo.id, 0)
        triados = estudo.concluidos + eliminados + estudo.em_coleta
        meta = estudo.participantes_necessarios
        linhas.append(
            {
                "estudo": estudo,
                "concluidos": estudo.concluidos,
                "eliminados": eliminados,
                "em_coleta": estudo.em_coleta,
                "triados": triados,
                "meta": meta,
                "progresso": min(100, _percentual(estudo.concluidos, meta)) if meta else None,
                "faixas": [
                    {"rotulo": "Concluídos", "classe": "concluidos", "total": estudo.concluidos,
                     "largura": _percentual(estudo.concluidos, triados)},
                    {"rotulo": "Eliminados", "classe": "eliminados", "total": eliminados,
                     "largura": _percentual(eliminados, triados)},
                    {"rotulo": "Em coleta", "classe": "em-coleta", "total": estudo.em_coleta,
                     "largura": _percentual(estudo.em_coleta, triados)},
                ],
                "criterios": eliminadas["por_criterio"].get(estudo.id, []),
            }
        )
    return linhas


def _por_semana(pesquisador):
    hoje = timezone.localdate()
    segunda = hoje - timedelta(days=hoje.weekday())
    inicio = segunda - timedelta(weeks=SEMANAS - 1)
    contagem = {}
    for modelo, data in ((Participacao, "tcle_aceito_em"), (RegistroAnonimo, "entrou_em")):
        filtro = {"estudo__pesquisador": pesquisador, f"{data}__date__gte": inicio}
        for semana, total in (
            modelo.objects.filter(**filtro).annotate(semana=TruncWeek(data)).values_list("semana").annotate(total=Count("id"))
        ):
            contagem[semana.date()] = contagem.get(semana.date(), 0) + total
    semanas = [inicio + timedelta(weeks=n) for n in range(SEMANAS)]
    maior = max([contagem.get(s, 0) for s in semanas] + [1])
    return [
        {"rotulo": s.strftime("%d/%m"), "total": contagem.get(s, 0), "altura": _percentual(contagem.get(s, 0), maior)}
        for s in semanas
    ]


def dados_do_painel(pesquisador):
    """Agregados dos estudos do pesquisador, sem CPF nem código de voluntário. Toda contagem sai do banco."""
    eliminadas = eliminacoes(pesquisador)
    estudos = _estudos(pesquisador, eliminadas)
    semanas = _por_semana(pesquisador)
    por_situacao = {valor: 0 for valor, _ in Estudo.Situacao.choices}
    for linha in estudos:
        por_situacao[linha["estudo"].situacao] += 1
    return {
        "estudos": estudos,
        "por_situacao": [(rotulo, por_situacao[valor]) for valor, rotulo in Estudo.Situacao.choices],
        "concluidos": sum(linha["concluidos"] for linha in estudos),
        "eliminados": eliminadas["total"],
        "semanas": semanas,
        "tem_coletas": any(semana["total"] for semana in semanas)
        or any(linha["triados"] for linha in estudos),
    }
