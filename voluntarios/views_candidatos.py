from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil
from estudos.views import estudo_do_pesquisador

from . import decisoes


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
    return redirect("estudos:classificacao", id=estudo.id)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def incluir(request, id):
    return _decidir(request, id, decisoes.incluir)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def recusar(request, id):
    return _decidir(request, id, decisoes.recusar)
