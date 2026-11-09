from django.contrib import messages
from django.db.models import Count
from django.http import Http404
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil
from catalogo.busca import buscar_criterios, selecionaveis
from catalogo.models import OpcaoDominio

from .forms import CriterioForm, EstudoForm, VariavelPropostaForm
from .models import Criterio, Estudo


def estudo_do_pesquisador(request, id):
    # Filtrar pelo dono aqui faz estudo alheio responder 404, sem confirmar que existe.
    return get_object_or_404(Estudo, pk=id, pesquisador=request.user)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def listar(request):
    estudos = Estudo.objects.filter(pesquisador=request.user).annotate(total_criterios=Count("criterios"))
    contexto = {
        "estudos": estudos,
        "total_ativos": estudos.filter(situacao=Estudo.Situacao.ATIVO).count(),
        "total_rascunhos": estudos.filter(situacao=Estudo.Situacao.RASCUNHO).count(),
        "total_encerrados": estudos.filter(situacao=Estudo.Situacao.ENCERRADO).count(),
    }
    return render(request, "estudos/lista.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def criar(request):
    form = EstudoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        estudo = form.save(commit=False)
        estudo.pesquisador = request.user
        estudo.save()
        registrar(RegistroAuditoria.Acao.ESTUDO_EDICAO, request=request, usuario=request.user, objeto=estudo.nome)
        return redirect("estudos:detalhe", id=estudo.id)
    return render(request, "estudos/formulario.html", {"form": form, "estudo": None})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def editar(request, id):
    estudo = estudo_do_pesquisador(request, id)
    form = EstudoForm(request.POST or None, instance=estudo)
    if request.method == "POST" and form.is_valid():
        form.save()
        registrar(RegistroAuditoria.Acao.ESTUDO_EDICAO, request=request, usuario=request.user, objeto=estudo.nome)
        return redirect("estudos:detalhe", id=estudo.id)
    return render(request, "estudos/formulario.html", {"form": form, "estudo": estudo})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def detalhe(request, id):
    estudo = estudo_do_pesquisador(request, id)
    registrar(RegistroAuditoria.Acao.ESTUDO_LEITURA, request=request, usuario=request.user, objeto=estudo.nome)
    return render(request, "estudos/detalhe.html", contexto_regras(estudo))


def variavel_selecionavel(variavel_id):
    return get_object_or_404(selecionaveis(), pk=variavel_id)


def contexto_regras(estudo):
    inclusao, exclusao = estudo.regras()
    return {"estudo": estudo, "inclusao": inclusao, "exclusao": exclusao, "resumo": estudo.resumo_texto}


def arvore_do_catalogo():
    # Agrupa em memória o que uma consulta só trouxe, na ordem do catálogo.
    arvore = []
    for variavel in selecionaveis().order_by("subcategoria__categoria__ordem", "subcategoria__ordem", "nome"):
        sub = variavel.subcategoria
        if not arvore or arvore[-1]["categoria"] != sub.categoria:
            arvore.append({"categoria": sub.categoria, "grupos": []})
        grupos = arvore[-1]["grupos"]
        if not grupos or grupos[-1]["subcategoria"] != sub:
            grupos.append({"subcategoria": sub, "variaveis": []})
        grupos[-1]["variaveis"].append(variavel)
    return arvore


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def criterios(request, id):
    estudo = estudo_do_pesquisador(request, id)
    contexto = contexto_regras(estudo)
    contexto["arvore"] = arvore_do_catalogo()
    inicial = request.GET.get("variavel", "")
    # Só variável que a tela abre de fato: um id inválido faria a configuração
    # responder 404 e o script recarregar a página sem parar.
    variavel = selecionaveis().filter(pk=int(inicial)).first() if inicial.isdigit() else None
    if variavel:
        contexto["configuracao_inicial"] = reverse("estudos:configurar_criterio", args=[estudo.id, variavel.id])
        contexto["variavel_inicial"] = variavel.id
        contexto["grupo_inicial"] = variavel.subcategoria_id
    return render(request, "estudos/criterios.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def buscar_variaveis(request, id):
    estudo = estudo_do_pesquisador(request, id)
    termo = request.GET.get("q", "").strip()
    contexto = {"estudo": estudo, "termo": termo, "variaveis": buscar_criterios(termo).select_related("subcategoria__categoria")[:30]}
    return render(request, "estudos/_resultados.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def configurar_criterio(request, id, variavel_id):
    estudo = estudo_do_pesquisador(request, id)
    variavel = variavel_selecionavel(variavel_id)
    form = CriterioForm(variavel=variavel)
    return render(request, "estudos/_configuracao.html", {"estudo": estudo, "variavel": variavel, "form": form})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def opcoes_filhas(request, id, variavel_id):
    estudo_do_pesquisador(request, id)
    variavel = variavel_selecionavel(variavel_id)
    pai = request.GET.get("pai", "")
    if not variavel.dominio.superior_id or not pai.isdigit():
        raise Http404
    # O pai tem de ser do domínio superior da variável, senão qualquer id listaria opções alheias.
    pai = get_object_or_404(OpcaoDominio, pk=int(pai), dominio_id=variavel.dominio.superior_id)
    return render(request, "estudos/_opcoes_filhas.html", {"opcoes": variavel.dominio.opcoes.filter(pai=pai)})


def criterio_da_requisicao(request, estudo, variavel, dados):
    form = CriterioForm(dados, variavel=variavel)
    form.instance.estudo = estudo
    return form


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def previa_criterio(request, id, variavel_id):
    estudo = estudo_do_pesquisador(request, id)
    form = criterio_da_requisicao(request, estudo, variavel_selecionavel(variavel_id), request.GET)
    completo = form.is_valid()
    contexto = {"completo": completo, "pendencia": form.pendencia(), "frase": form.instance.frase if completo else ""}
    return render(request, "estudos/_previa.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def adicionar_criterio(request, id, variavel_id):
    estudo = estudo_do_pesquisador(request, id)
    form = criterio_da_requisicao(request, estudo, variavel_selecionavel(variavel_id), request.POST)
    if not form.is_valid():
        contexto = {"completo": False, "pendencia": form.pendencia(), "frase": ""}
        return render(request, "estudos/_previa.html", contexto, status=422)
    form.save()
    return render(request, "estudos/_regras.html", contexto_regras(estudo))


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def propor_variavel(request, id):
    estudo = estudo_do_pesquisador(request, id)
    inicial = {}
    if request.GET.get("sub", "").isdigit():
        inicial["subcategoria"] = request.GET["sub"]
    if request.GET.get("nome"):
        inicial["nome"] = request.GET["nome"]

    form = VariavelPropostaForm(request.POST or None, initial=inicial)
    parecidas = []

    if request.method == "POST" and form.is_valid():
        parecidas = form.parecidas()
        if parecidas and not request.POST.get("confirmar"):
            messages.info(request, "Confira se alguma destas já serve antes de criar outra.")
        else:
            variavel = form.save()
            return redirect(f"{reverse('estudos:criterios', args=[estudo.id])}?variavel={variavel.id}")

    return render(
        request,
        "estudos/variavel_proposta.html",
        {"estudo": estudo, "form": form, "parecidas": parecidas},
    )


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def remover_criterio(request, id, criterio_id):
    estudo = estudo_do_pesquisador(request, id)
    get_object_or_404(Criterio, pk=criterio_id, estudo=estudo).delete()
    return render(request, "estudos/_regras.html", contexto_regras(estudo))
