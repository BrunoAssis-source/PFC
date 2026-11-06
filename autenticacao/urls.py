from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .forms import NovaSenhaForm, SolicitarSenhaForm
from .views import (
    EntrarView,
    RedefinirSenhaView,
    cadastrar,
    cadastro_enviado,
    confirmar_cadastro,
    coleta,
    criar_usuario,
    editar_usuario,
    excluir_usuario,
    inicio,
    meu_perfil,
    pendencias,
    politica_privacidade,
    reenviar_confirmacao,
    termos_de_uso,
    TrocarSenhaView,
    trocar_senha_usuario,
    usuarios,
)

urlpatterns = [
    path("", EntrarView.as_view(), name="login"),
    path("inicio/", inicio, name="inicio"),
    path("perfil/", meu_perfil, name="meu_perfil"),
    path("perfil/senha/", TrocarSenhaView.as_view(), name="trocar_senha"),
    path("coleta/", coleta, name="coleta"),
    path("pendencias/", pendencias, name="pendencias"),
    path("usuarios/", usuarios, name="usuarios"),
    path("usuarios/novo/", criar_usuario, name="criar_usuario"),
    path("usuarios/<int:usuario_id>/", editar_usuario, name="editar_usuario"),
    path("usuarios/<int:usuario_id>/excluir/", excluir_usuario, name="excluir_usuario"),
    path("usuarios/<int:usuario_id>/senha/", trocar_senha_usuario, name="trocar_senha_usuario"),
    path("cadastrar/", cadastrar, name="cadastro"),
    path("cadastrar/enviado/", cadastro_enviado, name="cadastro_enviado"),
    path("cadastrar/reenviar/", reenviar_confirmacao, name="reenviar_confirmacao"),
    path("cadastrar/confirmar/<uidb64>/<token>/", confirmar_cadastro, name="confirmar_cadastro"),
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
        RedefinirSenhaView.as_view(
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
    path("termos-de-uso/", termos_de_uso, name="termos_de_uso"),
]
