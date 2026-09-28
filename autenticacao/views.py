from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetConfirmView
from django.shortcuts import redirect, render

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar

from .forms import CadastroForm, LoginForm
from .models import Usuario
from .permissoes import exige_perfil


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


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def coleta(request):
    return render(request, "autenticacao/coleta.html")


@exige_perfil(Usuario.Perfil.PROFISSIONAL)
def pendencias(request):
    return render(request, "autenticacao/pendencias.html")


def politica_privacidade(request):
    return render(request, "autenticacao/politica_privacidade.html")


def termos_de_uso(request):
    return render(request, "autenticacao/termos_de_uso.html")


class RedefinirSenhaView(PasswordResetConfirmView):
    def form_valid(self, form):
        resposta = super().form_valid(form)
        registrar(RegistroAuditoria.Acao.SENHA_REDEFINIDA, request=self.request, usuario=form.user)
        return resposta
