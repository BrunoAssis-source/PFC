from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil
from estudos.models import Estudo
from estudos.views import estudo_do_pesquisador

from . import decisoes

SITUACOES = [("elegivel", "Elegíveis"), ("pendente", "Pendentes"), ("em_coleta", "Em coleta"), ("inelegivel", "Inelegíveis")]


def _decidir(request, id, acao):
    estudo = estudo_do_pesquisador(request, id)
    ids = [int(x) for x in request.POST.getlist("voluntarios") if x.isdigit()]
    relatorio = acao(estudo, ids, request.user, request)
    if relatorio["feitos"]:
        messages.success(request, f"{len(relatorio['feitos'])} candidato(s) com decisão registrada.")
    for codigo, motivo in relatorio["pulados"]:
        messages.warning(request, f"{codigo or 'Candidato'}: {motivo}.")
    meta = relatorio["meta"]
    if meta["necessarios"] is not None:
        texto = f"{meta['incluidos']} incluído(s) de {meta['necessarios']} necessário(s)."
        if meta["acima"]:
            texto += " A meta do estudo foi ultrapassada."
        messages.info(request, texto)
    return redirect("voluntarios:candidatos", id=estudo.id)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def candidatos(request, id):
    estudo = estudo_do_pesquisador(request, id)
    filtros = {
        "situacoes": [s for s in request.GET.getlist("situacao") if s in decisoes.SITUACOES] or ["elegivel"],
        "origem": request.GET.get("origem", ""),
        "decisao": request.GET.get("decisao", ""),
        "codigo": request.GET.get("codigo", "")[:64],
    }
    if filtros["origem"] not in ("deste", "outros"):
        filtros["origem"] = ""
    if filtros["decisao"] not in ("sem", "incluido", "recusado"):
        filtros["decisao"] = ""
    pagina = request.GET.get("pagina", "")
    contexto = {"estudo": estudo, "filtros": filtros, "situacoes": SITUACOES}
    if estudo.situacao == Estudo.Situacao.RASCUNHO:
        contexto["aviso"] = "Os candidatos aparecem quando o estudo estiver ativo."
    elif estudo.situacao == Estudo.Situacao.ATIVO and not estudo.criterios.exists():
        contexto["aviso"] = "Este estudo não tem critérios. Sem critérios não há o que avaliar."
    else:
        resultado = decisoes.candidatos(estudo, pagina=int(pagina) if pagina.isdigit() else 1, **filtros)
        consulta = urlencode(
            [("situacao", s) for s in filtros["situacoes"]] + [(k, v) for k, v in filtros.items() if v and k != "situacoes"]
        )
        contexto.update(resultado, somente_leitura=estudo.situacao != Estudo.Situacao.ATIVO, consulta=consulta)
    return render(request, "estudos/candidatos.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def incluir(request, id):
    return _decidir(request, id, decisoes.incluir)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def recusar(request, id):
    return _decidir(request, id, decisoes.recusar)
