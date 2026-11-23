from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil
from catalogo.models import OpcaoDominio
from estudos.models import Estudo, Tcle

from . import cpf as cpf_util
from .coleta import concluir_se_nao_ha_o_que_perguntar, proxima_variavel, registrar_resposta, respostas_pendentes
from .forms import CpfForm, RespostaForm, VinculoForm
from .models import TCLE_VERSAO_ATUAL, Participacao, Voluntario

Acao = RegistroAuditoria.Acao


def _auditar(request, acao, codigo=""):
    # O objeto leva só o começo do código, nunca o CPF.
    registrar(acao, request=request, usuario=request.user, objeto=codigo[:8])


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def identificar(request):
    form = CpfForm(request.POST or None)
    contexto = {"form": form, "ausente": None}
    if request.method == "POST" and form.is_valid():
        numeros = form.cleaned_data["cpf"]
        codigo = cpf_util.codigo(numeros)
        voluntario = Voluntario.objects.filter(codigo_hmac=codigo).first()
        _auditar(request, Acao.VOLUNTARIO_BUSCA, codigo)
        if voluntario:
            return redirect("voluntarios:detalhe", id=voluntario.id)
        contexto["ausente"] = cpf_util.mascarar(numeros)
        contexto["cpf"] = numeros
    return render(request, "voluntarios/identificar.html", contexto)


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
@require_POST
def cadastrar(request):
    form = CpfForm(request.POST)
    if not form.is_valid():
        messages.error(request, "CPF inválido. Confira os 11 dígitos.")
        return redirect("voluntarios:identificar")
    numeros = form.cleaned_data["cpf"]
    codigo = cpf_util.codigo(numeros)
    try:
        with transaction.atomic():
            voluntario = Voluntario.objects.create(
                codigo_hmac=codigo, cpf_cifrado=cpf_util.cifrar(numeros), criado_por=request.user
            )
    except IntegrityError:
        # Outro profissional cadastrou o mesmo CPF entre a busca e este envio.
        voluntario = Voluntario.objects.get(codigo_hmac=codigo)
        _auditar(request, Acao.VOLUNTARIO_DUPLICADO, codigo)
        messages.info(request, "Este voluntário já estava cadastrado.")
    else:
        _auditar(request, Acao.VOLUNTARIO_CADASTRO, codigo)
        messages.success(request, "Voluntário cadastrado.")
    return redirect("voluntarios:detalhe", id=voluntario.id)


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def detalhe(request, id):
    voluntario = get_object_or_404(Voluntario, pk=id)
    _auditar(request, Acao.VOLUNTARIO_LEITURA, voluntario.codigo_hmac)
    contexto = {
        "voluntario": voluntario,
        "cpf_mascarado": cpf_util.mascarar(cpf_util.decifrar(voluntario.cpf_cifrado)),
        "pagina": Paginator(voluntario.participacoes.select_related("estudo").order_by("-id"), 10).get_page(
            request.GET.get("pagina")
        ),
        "form": VinculoForm(),
    }
    return render(request, "voluntarios/detalhe.html", contexto)


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
@require_POST
def vincular(request, id):
    voluntario = get_object_or_404(Voluntario, pk=id)
    form = VinculoForm(request.POST)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect("voluntarios:detalhe", id=voluntario.id)
    estudo = form.cleaned_data["estudo"]
    if not estudo.tem_tcle:
        # A tela trava a caixa, mas o servidor também recusa: não há termo para conferir.
        messages.error(request, "O pesquisador ainda não anexou o TCLE deste estudo.")
        return redirect("voluntarios:detalhe", id=voluntario.id)
    participacao, criada = Participacao.objects.get_or_create(
        voluntario=voluntario,
        estudo=estudo,
        defaults={"tcle_versao": TCLE_VERSAO_ATUAL, "registrado_por": request.user},
    )
    objeto = f"{voluntario.codigo_hmac[:8]} em {estudo.nome}"
    if criada:
        registrar(Acao.PARTICIPACAO_VINCULO, request=request, usuario=request.user, objeto=objeto)
    if request.POST.get("seguir") == "coleta":
        # Vindo da lista de pendências: segue direto para a coleta, que pede só o que falta.
        registrar(Acao.PENDENCIA_COLETA, request=request, usuario=request.user, objeto=objeto)
        return redirect("voluntarios:coleta", id=voluntario.id, participacao_id=participacao.id)
    if criada:
        messages.success(request, "Voluntário vinculado ao estudo.")
    else:
        messages.info(request, "Este voluntário já participa do estudo.")
    return redirect("voluntarios:detalhe", id=voluntario.id)


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def tcle_do_estudo(request, id):
    # Só estudo ativo: é o único em que o profissional confere o termo assinado.
    estudo = get_object_or_404(Estudo, pk=id, situacao=Estudo.Situacao.ATIVO)
    tcle = Tcle.objects.filter(estudo=estudo).first()
    if tcle is None:
        # Estudo ativado antes de o anexo ser obrigatório: avisa em vez de mostrar página de erro.
        messages.error(request, "O pesquisador ainda não anexou o TCLE deste estudo.")
        return redirect(request.META.get("HTTP_REFERER") or "voluntarios:identificar")
    resposta = HttpResponse(bytes(tcle.conteudo), content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{tcle.nome_arquivo.replace(chr(34), "")}"'
    return resposta


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def coletar(request, id, participacao_id):
    participacao = get_object_or_404(
        Participacao.objects.select_related("estudo", "voluntario"), pk=participacao_id, voluntario_id=id
    )
    if participacao.estudo.situacao != Estudo.Situacao.ATIVO:
        messages.error(request, "Este estudo não está ativo.")
        return redirect("voluntarios:detalhe", id=id)
    em_coleta = participacao.situacao == Participacao.Situacao.EM_COLETA
    if not em_coleta and participacao.situacao not in (Participacao.Situacao.ELIMINADA, Participacao.Situacao.CONCLUIDA):
        return redirect("voluntarios:detalhe", id=id)

    pendentes = respostas_pendentes(request.session, participacao)
    variavel = proxima_variavel(participacao, pendentes) if em_coleta else None
    if em_coleta and variavel is None:
        concluir_se_nao_ha_o_que_perguntar(participacao)
        em_coleta = False

    if em_coleta and request.method == "POST" and request.POST.get("variavel") == str(variavel.id):
        form = RespostaForm(request.POST, variavel=variavel)
        if form.is_valid():
            if variavel.sensivel:
                acao = Acao.SENSIVEL_RESPOSTA
            else:
                acao = Acao.COLETA_RESPOSTA
            resultado = registrar_resposta(
                participacao, variavel, form.valores(), form.cleaned_data["fonte"], request.user, request.session
            )
            registrar(
                acao,
                request=request,
                usuario=request.user,
                objeto=f"{participacao.voluntario.codigo_hmac[:8]} {variavel.codigo}",
            )
            if resultado == "eliminada":
                registrar(
                    Acao.COLETA_ELIMINACAO,
                    request=request,
                    usuario=request.user,
                    objeto=f"{participacao.voluntario.codigo_hmac[:8]} em {participacao.estudo.nome}",
                )
            # Resposta e fim da coleta voltam pela mesma rota, sem dado da variável que reprovou.
            return redirect("voluntarios:coleta", id=id, participacao_id=participacao.id)
    elif em_coleta:
        form = RespostaForm(variavel=variavel)

    if em_coleta:
        contexto = {"participacao": participacao, "variavel": variavel, "form": form}
        if variavel.dominio_id and variavel.dominio.superior_id:
            contexto["estados"] = variavel.dominio.superior.opcoes.all()
            contexto["url_filhas"] = reverse("voluntarios:opcoes_filhas", args=[id, participacao.id])
        return render(request, "voluntarios/coleta.html", contexto)
    return render(request, "voluntarios/coleta_encerrada.html", {"participacao": participacao, "eliminada": participacao.situacao == Participacao.Situacao.ELIMINADA})


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def opcoes_filhas(request, id, participacao_id):
    participacao = get_object_or_404(
        Participacao.objects.select_related("estudo"),
        pk=participacao_id,
        voluntario_id=id,
        situacao=Participacao.Situacao.EM_COLETA,
    )
    # Só a variável que está sendo perguntada, senão o endpoint listaria o domínio de qualquer variável.
    variavel = proxima_variavel(participacao, respostas_pendentes(request.session, participacao))
    pai = request.GET.get("pai", "")
    if variavel is None or not variavel.dominio_id or not variavel.dominio.superior_id or not pai.isdigit():
        raise Http404
    pai = get_object_or_404(OpcaoDominio, pk=int(pai), dominio_id=variavel.dominio.superior_id)
    return render(
        request, "estudos/_opcoes_filhas.html", {"opcoes": variavel.dominio.opcoes.filter(pai=pai), "tipo": "radio"}
    )
