import logging
import math
import time

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetConfirmView
from django.core.paginator import Paginator
from django.core.mail import EmailMultiAlternatives
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar
from estudos.painel import dados_do_painel

from .forms import (
    CadastroForm,
    LoginForm,
    MeuPerfilForm,
    CodigoConfirmacaoForm,
    NovaSenhaForm,
    ReenviarConfirmacaoForm,
    TrocarSenhaForm,
    UsuarioCriacaoForm,
    UsuarioEdicaoForm,
)
from .confirmacao import INTERVALO_ENVIO, LimiteDeEnvio, emitir, encerrar, validar_codigo, validar_link
from .models import Usuario
from .permissoes import exige_administrador, exige_perfil, recusa_alterar_superusuario


logger = logging.getLogger(__name__)


class EntrarView(LoginView):
    authentication_form = LoginForm
    template_name = "autenticacao/login.html"
    redirect_authenticated_user = True


def espera_restante(request):
    # A contagem parte do pedido, exista ou não o cadastro, para não revelar quais emails estão cadastrados.
    decorrido = time.time() - request.session.get("confirmacao_pedida_em", 0)
    return max(0, math.ceil(INTERVALO_ENVIO.total_seconds() - decorrido))


def ativar_conta(request, usuario):
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
    encerrar(usuario)
    registrar(RegistroAuditoria.Acao.CADASTRO, request=request, usuario=usuario, objeto="email confirmado")


def enviar_confirmacao(request, usuario):
    try:
        codigo, segredo = emitir(usuario)
    except LimiteDeEnvio:
        # Fica em silêncio para a resposta ser igual exista ou não o cadastro. A tela informa os limites.
        return
    link = request.build_absolute_uri(
        reverse(
            "confirmar_cadastro",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(usuario.pk)),
                "token": segredo,
            },
        )
    )
    contexto = {"usuario": usuario, "link": link, "codigo": codigo}
    mensagem = EmailMultiAlternatives(
        "Confirme seu cadastro no UniData",
        render_to_string("autenticacao/cadastro_email.txt", contexto),
        to=[usuario.email],
    )
    mensagem.attach_alternative(render_to_string("autenticacao/cadastro_email.html", contexto), "text/html")
    try:
        mensagem.send()
    except Exception:
        # A conta já existe e a pessoa pode pedir o link de novo, então a falha do envio não derruba o cadastro.
        logger.exception("Falha ao enviar a confirmação de cadastro.")


def cadastrar(request):
    if request.user.is_authenticated:
        return redirect("inicio")

    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save(commit=False)
        usuario.is_active = False
        usuario.save()
        registrar(RegistroAuditoria.Acao.CADASTRO, request=request, usuario=usuario)
        enviar_confirmacao(request, usuario)
        request.session["email_confirmacao"] = usuario.email
        request.session["confirmacao_pedida_em"] = time.time()
        return redirect("cadastro_enviado")
    return render(request, "autenticacao/cadastro.html", {"form": form})


def cadastro_enviado(request):
    email = request.session.get("email_confirmacao", "")
    form = CodigoConfirmacaoForm(request.POST or None)
    if email:
        # O email já foi digitado na tela anterior, então só o código é pedido.
        del form.fields["email"]
    if request.method == "POST" and form.is_valid():
        usuario = Usuario.objects.filter(email__iexact=email or form.cleaned_data["email"]).first()
        if usuario and usuario.aguarda_confirmacao and validar_codigo(usuario, form.cleaned_data["codigo"]):
            ativar_conta(request, usuario)
            return render(request, "autenticacao/cadastro_confirmacao.html", {"valido": True})
        form.add_error("codigo", "Código incorreto, vencido ou substituído por um envio mais novo. Peça um novo envio se precisar.")
    return render(request, "autenticacao/cadastro_enviado.html", {"form": form, "espera": espera_restante(request), "email": email})


def confirmar_cadastro(request, uidb64, token):
    try:
        usuario = Usuario.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
        usuario = None

    if usuario is not None and usuario.is_active:
        return render(request, "autenticacao/cadastro_confirmacao.html", {"valido": True})
    if usuario is None or not usuario.aguarda_confirmacao or not validar_link(usuario, token):
        return render(request, "autenticacao/cadastro_confirmacao.html", {"valido": False})

    ativar_conta(request, usuario)
    return render(request, "autenticacao/cadastro_confirmacao.html", {"valido": True})


def reenviar_confirmacao(request):
    form = ReenviarConfirmacaoForm(request.POST or None, initial={"email": request.session.get("email_confirmacao", "")})
    espera = espera_restante(request)
    if request.method == "POST" and form.is_valid() and not espera:
        usuario = Usuario.objects.filter(email__iexact=form.cleaned_data["email"]).first()
        if usuario and usuario.aguarda_confirmacao:
            enviar_confirmacao(request, usuario)
        # A resposta é a mesma exista ou não o cadastro, para não revelar quais emails estão cadastrados.
        request.session["email_confirmacao"] = form.cleaned_data["email"]
        request.session["confirmacao_pedida_em"] = time.time()
        return redirect("cadastro_enviado")
    return render(request, "autenticacao/cadastro_reenviar.html", {"form": form, "espera": espera})


@login_required
def inicio(request):
    contexto = {}
    if request.user.e_pesquisador:
        contexto["painel"] = dados_do_painel(request.user)
    return render(request, "autenticacao/inicio.html", contexto)


@login_required
def meu_perfil(request):
    form = MeuPerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        registrar(RegistroAuditoria.Acao.USUARIO_EDICAO, request=request, usuario=request.user, objeto=request.user.email)
        messages.success(request, "Seus dados foram atualizados.")
        return redirect("meu_perfil")
    return render(request, "autenticacao/meu_perfil.html", {"form": form})


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def coleta(request):
    return render(request, "autenticacao/coleta.html")


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def pendencias(request):
    return render(request, "autenticacao/pendencias.html")


@exige_administrador
def usuarios(request):
    busca = request.GET.get("q", "").strip()
    perfil = request.GET.get("perfil", "")
    situacao = request.GET.get("situacao", "")
    administrador = request.GET.get("administrador", "")

    consulta = Usuario.objects.order_by("nome_completo")
    if busca:
        consulta = consulta.filter(Q(nome_completo__icontains=busca) | Q(email__icontains=busca))
    if perfil in Usuario.Perfil.values:
        consulta = consulta.filter(perfil=perfil)
    if situacao in ("ativo", "inativo"):
        consulta = consulta.filter(is_active=situacao == "ativo")
    if administrador == "sim":
        consulta = consulta.filter(is_staff=True)

    filtros = request.GET.copy()
    filtros.pop("pagina", None)
    contexto = {
        "pagina": Paginator(consulta, 50).get_page(request.GET.get("pagina")),
        "perfis": Usuario.Perfil.choices,
        "busca": busca,
        "perfil": perfil,
        "situacao": situacao,
        "administrador": administrador,
        "filtros": filtros.urlencode(),
    }
    return render(request, "autenticacao/usuarios.html", contexto)


@exige_administrador
def criar_usuario(request):
    form = UsuarioCriacaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        novo = form.save()
        registrar(RegistroAuditoria.Acao.CADASTRO, request=request, usuario=request.user, objeto=novo.email)
        messages.success(request, "Usuário criado.")
        return redirect("usuarios")
    return render(request, "autenticacao/usuario_formulario.html", {"form": form, "titulo": "Novo usuário", "botao": "Criar usuário"})


@exige_administrador
def trocar_senha_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    recusa_alterar_superusuario(request, usuario)
    form = NovaSenhaForm(usuario, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        # Sem isto a troca da própria senha encerraria a sessão do administrador.
        if usuario == request.user:
            update_session_auth_hash(request, usuario)
        registrar(RegistroAuditoria.Acao.SENHA_REDEFINIDA, request=request, usuario=request.user, objeto=usuario.email)
        messages.success(request, "Senha alterada.")
        return redirect("editar_usuario", usuario_id=usuario.pk)
    contexto = {"form": form, "usuario": usuario, "titulo": "Alterar senha", "botao": "Alterar senha"}
    return render(request, "autenticacao/usuario_formulario.html", contexto)


@exige_administrador
def editar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    recusa_alterar_superusuario(request, usuario)
    form = UsuarioEdicaoForm(
        request.POST or None,
        instance=usuario,
        editando_a_si_mesmo=usuario == request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        registrar(RegistroAuditoria.Acao.USUARIO_EDICAO, request=request, usuario=request.user, objeto=usuario.email)
        messages.success(request, "Dados do usuário atualizados.")
        return redirect("usuarios")
    contexto = {"form": form, "usuario": usuario, "titulo": "Editar usuário", "botao": "Salvar alterações", "pode_trocar_senha": True, "pode_excluir": usuario != request.user}
    return render(request, "autenticacao/usuario_formulario.html", contexto)


@exige_administrador
def excluir_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    recusa_alterar_superusuario(request, usuario)
    if usuario == request.user:
        messages.error(request, "Você não pode excluir a própria conta.")
        return redirect("editar_usuario", usuario_id=usuario.pk)

    if request.method == "POST":
        email = usuario.email
        try:
            usuario.delete()
        except ProtectedError:
            messages.error(request, "Este usuário tem estudos cadastrados e não pode ser excluído. Desative a conta pela edição.")
            return redirect("editar_usuario", usuario_id=usuario.pk)
        registrar(RegistroAuditoria.Acao.USUARIO_EXCLUSAO, request=request, usuario=request.user, objeto=email)
        messages.success(request, "Usuário excluído.")
        return redirect("usuarios")
    return render(request, "autenticacao/usuario_exclusao.html", {"usuario": usuario})


def politica_privacidade(request):
    return render(request, "autenticacao/politica_privacidade.html")


def termos_de_uso(request):
    return render(request, "autenticacao/termos_de_uso.html")


class RedefinirSenhaView(PasswordResetConfirmView):
    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar(RegistroAuditoria.Acao.SENHA_REDEFINIDA, request=self.request, usuario=form.user)
        return resposta


class TrocarSenhaView(PasswordChangeView):
    template_name = "autenticacao/trocar_senha.html"
    form_class = TrocarSenhaForm
    success_url = reverse_lazy("meu_perfil")

    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar(RegistroAuditoria.Acao.SENHA_REDEFINIDA, request=self.request, usuario=self.request.user, objeto=self.request.user.email)
        messages.success(self.request, "Senha alterada.")
        return resposta
