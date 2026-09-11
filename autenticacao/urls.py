from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .forms import NovaSenhaForm, SolicitarSenhaForm
from .views import (
    EntrarView,
    cadastrar,
    coleta,
    inicio,
    pendencias,
    politica_privacidade,
)

urlpatterns = [
    path("", EntrarView.as_view(), name="login"),
    path("inicio/", inicio, name="inicio"),
    path("coleta/", coleta, name="coleta"),
    path("pendencias/", pendencias, name="pendencias"),
    path("cadastrar/", cadastrar, name="cadastro"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "senha/esqueci/",
        auth_views.PasswordResetView.as_view(
            template_name="autenticacao/senha_reset.html",
            email_template_name="autenticacao/senha_reset_email.txt",
            html_email_template_name="autenticacao/senha_reset_email.html",
            subject_template_name="autenticacao/senha_reset_assunto.txt",
            form_class=SolicitarSenhaForm,
            success_url=reverse_lazy("senha_reset_done"),
        ),
        name="senha_reset",
    ),
    path(
        "senha/esqueci/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="autenticacao/senha_reset_enviado.html"),
        name="senha_reset_done",
    ),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="autenticacao/senha_confirmar.html",
            form_class=NovaSenhaForm,
            success_url=reverse_lazy("senha_reset_complete"),
        ),
        name="senha_reset_confirm",
    ),
    path(
        "senha/redefinida/",
        auth_views.PasswordResetCompleteView.as_view(template_name="autenticacao/senha_redefinida.html"),
        name="senha_reset_complete",
    ),
    path("politica-de-privacidade/", politica_privacidade, name="politica_privacidade"),
]
