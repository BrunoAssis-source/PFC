from django.contrib import messages
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil
from catalogo.busca import buscar_criterios, selecionaveis
from catalogo.models import OpcaoDominio

from voluntarios.pendencias import sincronizar_notificacoes

from .forms import CriterioForm, EstudoForm, VariavelPropostaForm
from .models import Criterio, Estudo


def estudo_do_pesquisador(request, id):
    # Filtrar pelo dono aqui faz estudo alheio responder 404, sem confirmar que existe.
    return get_object_or_404(Estudo, pk=id, pesquisador=request.user)


def estudo_editavel(request, id):
    # RN20: estudo encerrado não aceita inclusão, alteração nem remoção de critérios, e o servidor recusa mesmo
    # quando a tela não oferece o botão.
    estudo = estudo_do_pesquisador(request, id)
    if estudo.situacao == Estudo.Situacao.ENCERRADO:
        raise PermissionDenied("Estudo encerrado não aceita alteração de critérios.")
    return estudo


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
        # Ativar o estudo pode deixar voluntários já registrados pendentes.
        sincronizar_notificacoes(estudo=estudo)
        return redirect("estudos:detalhe", id=estudo.id)
    return render(request, "estudos/formulario.html", {"form": form, "estudo": estudo})


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def detalhe(request, id):
    estudo = estudo_do_pesquisador(request, id)
    registrar(RegistroAuditoria.Acao.ESTUDO_LEITURA, request=request, usuario=request.user, objeto=estudo.nome)
    contexto = contexto_regras(estudo)
    contexto["eliminadas"] = estudo.participacoes.filter(situacao="eliminada").select_related(
        "voluntario", "criterio_reprovado__variavel"
    ).order_by("-encerrada_em")
    return render(request, "estudos/detalhe.html", contexto)


def variavel_selecionavel(variavel_id):
    return get_object_or_404(selecionaveis(), pk=variavel_id)


def contexto_regras(estudo):
    inclusao, exclusao = estudo.regras()
    usadas = {criterio.variavel_id for criterio in inclusao + exclusao}
    return {
        "estudo": estudo, "inclusao": inclusao, "exclusao": exclusao, "resumo": estudo.resumo_texto,
        "usadas_ids": usadas, "usadas": ",".join(map(str, sorted(usadas))),
    }


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
    contexto["somente_leitura"] = estudo.situacao == Estudo.Situacao.ENCERRADO
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
    variaveis = buscar_criterios(termo).select_related("subcategoria__categoria")
    if request.GET.get("sub", "").isdigit():
        variaveis = variaveis.filter(subcategoria_id=int(request.GET["sub"]))
    variaveis = variaveis[:60]
    contexto = {
        "estudo": estudo, "termo": termo, "usadas_ids": set(estudo.criterios.values_list("variavel_id", flat=True)),
        "variaveis": variaveis,
    }
    return render(request, "estudos/_resultados.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def configurar_criterio(request, id, variavel_id):
    estudo = estudo_editavel(request, id)
    variavel = variavel_selecionavel(variavel_id)
    return render(request, "estudos/_configuracao.html", contexto_configuracao(estudo, variavel))


def contexto_configuracao(estudo, variavel, criterio=None):
    """Contexto da coluna do meio, em branco ou preenchido com o critério em edição."""
    contexto = {
        "estudo": estudo, "variavel": variavel, "form": CriterioForm(variavel=variavel),
        "criterio": criterio, "selecionadas": [], "marcadas": [], "valores": {"precisao": Criterio.Precisao.DIA},
    }
    if criterio:
        contexto["selecionadas"] = list(criterio.opcoes.all())
        contexto["marcadas"] = [opcao.pk for opcao in contexto["selecionadas"]]
        contexto["valores"] = {
            "valor": numero_do_campo(criterio.valor_numero),
            "ate": numero_do_campo(criterio.valor_numero_ate),
            "precisao": criterio.precisao,
        }
        for sufixo, data in (("", criterio.valor_data), ("_ate", criterio.valor_data_ate)):
            if data:
                contexto["valores"].update(
                    {f"ano{sufixo}": data.year, f"mes{sufixo}": data.month, f"dia{sufixo}": data.day}
                )
    return contexto


def numero_do_campo(valor):
    # O campo type=number só entende ponto decimal e não quer zeros à direita.
    return "" if valor is None else format(valor.normalize(), "f")


@exige_perfil(Usuario.Perfil.PESQUISADOR)
def opcoes_filhas(request, id, variavel_id):
    estudo_editavel(request, id)
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
@require_POST
def previa_criterio(request, id, variavel_id):
    # POST porque uma lista grande de municípios não cabe no endereço da requisição.
    estudo = estudo_editavel(request, id)
    form = criterio_da_requisicao(request, estudo, variavel_selecionavel(variavel_id), request.POST)
    completo = form.is_valid()
    contexto = {"completo": completo, "pendencia": form.pendencia(), "frase": form.instance.frase if completo else ""}
    return render(request, "estudos/_previa.html", contexto)


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_POST
def adicionar_criterio(request, id, variavel_id):
    estudo = estudo_editavel(request, id)
    form = criterio_da_requisicao(request, estudo, variavel_selecionavel(variavel_id), request.POST)
    if not form.is_valid():
        contexto = {"completo": False, "pendencia": form.pendencia(), "frase": ""}
        return render(request, "estudos/_previa.html", contexto, status=422)
    form.save()
    registrar(
        RegistroAuditoria.Acao.CRITERIO_ADICAO, request=request, usuario=request.user,
        objeto=f"{estudo.nome}. {form.instance.frase}",
    )
    sincronizar_notificacoes(estudo=estudo)
    return render(request, "estudos/_regras.html", contexto_regras(estudo))


@exige_perfil(Usuario.Perfil.PESQUISADOR)
@require_http_methods(["GET", "POST"])
def editar_criterio(request, id, criterio_id):
    estudo = estudo_editavel(request, id)
    criterio = get_object_or_404(Criterio.objects.select_related("variavel"), pk=criterio_id, estudo=estudo)
    if request.method == "GET":
        return render(request, "estudos/_configuracao.html", contexto_configuracao(estudo, criterio.variavel, criterio))

    # A frase antes tem de sair já, porque validar o formulário altera a instância.
    antes = criterio.frase
    form = CriterioForm(request.POST, variavel=criterio.variavel, instance=criterio)
    if not form.is_valid():
        contexto = {"completo": False, "pendencia": form.pendencia(), "frase": ""}
        return render(request, "estudos/_previa.html", contexto, status=422)
    form.save()
    if criterio.frase != antes:
        registrar(
            RegistroAuditoria.Acao.CRITERIO_EDICAO, request=request, usuario=request.user,
            objeto=f"{estudo.nome}. Antes: {antes}. Depois: {criterio.frase}",
        )
    sincronizar_notificacoes(estudo=estudo)
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
    estudo = estudo_editavel(request, id)
    criterio = get_object_or_404(Criterio, pk=criterio_id, estudo=estudo)
    frase = criterio.frase
    criterio.delete()
    registrar(
        RegistroAuditoria.Acao.CRITERIO_REMOCAO, request=request, usuario=request.user,
        objeto=f"{estudo.nome}. {frase}",
    )
    sincronizar_notificacoes(estudo=estudo)
    return render(request, "estudos/_regras.html", contexto_regras(estudo))
