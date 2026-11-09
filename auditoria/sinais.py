from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import RegistroAuditoria
from .servicos import registrar


@receiver(user_logged_in)
def ao_logar(sender, request, user, **kwargs):
    registrar(RegistroAuditoria.Acao.LOGIN_SUCESSO, request=request, usuario=user)


@receiver(user_logged_out)
def ao_sair(sender, request, user, **kwargs):
    if user is not None:
        registrar(RegistroAuditoria.Acao.LOGOUT, request=request, usuario=user)


@receiver(user_login_failed)
def ao_falhar_login(sender, credentials, request, **kwargs):
    registrar(
        RegistroAuditoria.Acao.LOGIN_FALHA,
        request=request,
        email_tentativa=credentials.get("username", ""),
    )
