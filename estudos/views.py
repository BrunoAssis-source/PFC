from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil
from catalogo.models import Categoria, Subcategoria, Variavel, normalizar

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
        return redirect("estudos:detalhe", id=estudo.id)
    return render(request, "estudos/formulario.html", {"form": form, "estudo": None})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def editar(request, id):
    estudo = estudo_do_pesquisador(request, id)
    form = EstudoForm(request.POST or None, instance=estudo)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("estudos:detalhe", id=estudo.id)
    return render(request, "estudos/formulario.html", {"form": form, "estudo": estudo})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def detalhe(request, id):
    estudo = estudo_do_pesquisador(request, id)
    criterios = estudo.criterios.select_related("variavel", "variavel__subcategoria").prefetch_related("opcoes")
    return render(request, "estudos/detalhe.html", {"estudo": estudo, "criterios": criterios})


def variaveis_selecionaveis():
    # Categórica só entra com domínio; as que dependem de tabela de referência ficam fora.
    return (
        Variavel.objects.exclude(tipo=Variavel.Tipo.TEXTO)
        .filter(Q(dominio__isnull=False) | Q(tipo__in=["numerica", "data", "booleana"]))
        .select_related("subcategoria", "subcategoria__categoria")
    )


def contar(selecionaveis, campo):
    return dict(selecionaveis.values_list(campo).annotate(total=Count("id")))


def preparar_variaveis(variaveis, estudo):
    ja_criterio = set(estudo.criterios.values_list("variavel_id", flat=True))
    for variavel in variaveis:
        variavel.ja_e_criterio = variavel.id in ja_criterio
    return variaveis


def montar_seletor(request, estudo):
    termo = normalizar(request.GET.get("q", "").strip())
    categoria_id = request.GET.get("cat", "")
    subcategoria_id = request.GET.get("sub", "")

    selecionaveis = variaveis_selecionaveis()
    contexto = {
        "estudo": estudo,
        "termo": request.GET.get("q", ""),
        "subcategoria_ativa": subcategoria_id,
    }

    if termo:
        variaveis = selecionaveis.filter(busca__contains=termo)
        chips = (
            Subcategoria.objects.filter(variaveis__in=variaveis)
            .select_related("categoria")
            .annotate(total=Count("variaveis"))
            .order_by("categoria__ordem", "ordem")
        )
        if subcategoria_id.isdigit():
            variaveis = variaveis.filter(subcategoria_id=int(subcategoria_id))
        contexto.update(
            modo="busca",
            chips=chips,
            variaveis=preparar_variaveis(list(variaveis.order_by("subcategoria__ordem", "nome")[:60]), estudo),
        )
        return contexto

    if subcategoria_id.isdigit():
        subcategoria = get_object_or_404(Subcategoria.objects.select_related("categoria"), pk=subcategoria_id)
        variaveis = selecionaveis.filter(subcategoria=subcategoria).order_by("nome")
        contexto.update(
            modo="variaveis",
            subcategoria=subcategoria,
            categoria=subcategoria.categoria,
            variaveis=preparar_variaveis(list(variaveis), estudo),
        )
        return contexto

    if categoria_id.isdigit():
        categoria = get_object_or_404(Categoria, pk=categoria_id)
        totais = contar(selecionaveis, "subcategoria_id")
        subcategorias = [s for s in categoria.subcategorias.all() if totais.get(s.id)]
        for sub in subcategorias:
            sub.total = totais[sub.id]
        contexto.update(modo="subcategorias", categoria=categoria, subcategorias=subcategorias)
        return contexto

    totais = contar(selecionaveis, "subcategoria__categoria_id")
    categorias = [c for c in Categoria.objects.all() if totais.get(c.id)]
    for categoria in categorias:
        categoria.total = totais[categoria.id]
    contexto.update(modo="categorias", categorias=categorias)
    return contexto


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def escolher_variavel(request, id):
    estudo = estudo_do_pesquisador(request, id)
    return render(request, "estudos/criterio_variavel.html", montar_seletor(request, estudo))


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def lista_variaveis(request, id):
    estudo = estudo_do_pesquisador(request, id)
    return render(request, "estudos/_resultados_variaveis.html", montar_seletor(request, estudo))


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
            return redirect("estudos:criar_criterio", id=estudo.id, variavel_id=variavel.id)

    return render(
        request,
        "estudos/variavel_proposta.html",
        {"estudo": estudo, "form": form, "parecidas": parecidas},
    )


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def criar_criterio(request, id, variavel_id):
    estudo = estudo_do_pesquisador(request, id)
    variavel = get_object_or_404(variaveis_selecionaveis(), pk=variavel_id)

    form = CriterioForm(request.POST or None, variavel=variavel)
    if request.method == "POST" and form.is_valid():
        criterio = form.save(commit=False)
        criterio.estudo = estudo
        criterio.variavel = variavel
        criterio.save()
        form.save_m2m()
        try:
            criterio.validar_opcoes()
        except ValidationError as erro:
            criterio.delete()
            form.add_error(None, erro)
        else:
            messages.success(request, "Critério adicionado.")
            return redirect("estudos:detalhe", id=estudo.id)

    return render(request, "estudos/criterio_formulario.html", {"estudo": estudo, "variavel": variavel, "form": form})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def remover_criterio(request, id, criterio_id):
    estudo = estudo_do_pesquisador(request, id)
    criterio = get_object_or_404(Criterio, pk=criterio_id, estudo=estudo)
    if request.method == "POST":
        criterio.delete()
        messages.success(request, "Critério removido.")
    return redirect("estudos:detalhe", id=estudo.id)
