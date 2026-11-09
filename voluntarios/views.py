from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from autenticacao.models import Usuario
from autenticacao.permissoes import exige_perfil

from . import cpf as cpf_util
from .forms import CpfForm, VinculoForm
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
        "participacoes": voluntario.participacoes.select_related("estudo"),
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
    _, criada = Participacao.objects.get_or_create(
        voluntario=voluntario,
        estudo=estudo,
        defaults={"tcle_versao": TCLE_VERSAO_ATUAL, "registrado_por": request.user},
    )
    if criada:
        registrar(
            Acao.PARTICIPACAO_VINCULO,
            request=request,
            usuario=request.user,
            objeto=f"{voluntario.codigo_hmac[:8]} em {estudo.nome}",
        )
        messages.success(request, "Voluntário vinculado ao estudo.")
    else:
        messages.info(request, "Este voluntário já participa do estudo.")
    return redirect("voluntarios:detalhe", id=voluntario.id)
