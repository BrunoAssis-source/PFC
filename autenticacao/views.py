from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetConfirmView
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar

from .forms import CadastroForm, LoginForm, MeuPerfilForm, NovaSenhaForm, UsuarioCriacaoForm, UsuarioEdicaoForm
from .models import Usuario
from .permissoes import exige_administrador, exige_perfil, recusa_alterar_superusuario


class EntrarView(LoginView):
    authentication_form = LoginForm
    template_name = "autenticacao/login.html"
    redirect_authenticated_user = True


def cadastrar(request):
    if request.user.is_authenticated:
        return redirect("inicio")

    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        registrar(RegistroAuditoria.Acao.CADASTRO, request=request, usuario=usuario)
        login(request, usuario)
        return redirect("inicio")
    return render(request, "autenticacao/cadastro.html", {"form": form})


@login_required
def inicio(request):
    return render(request, "autenticacao/inicio.html")


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
    contexto = {"form": form, "usuario": usuario, "titulo": "Editar usuário", "botao": "Salvar alterações", "pode_trocar_senha": True}
    return render(request, "autenticacao/usuario_formulario.html", contexto)


def politica_privacidade(request):
    return render(request, "autenticacao/politica_privacidade.html")


def termos_de_uso(request):
    return render(request, "autenticacao/termos_de_uso.html")


class RedefinirSenhaView(PasswordResetConfirmView):
    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar(RegistroAuditoria.Acao.SENHA_REDEFINIDA, request=self.request, usuario=form.user)
        return resposta
