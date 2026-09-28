from .models import RegistroAuditoria


def enderecar_ip(request):
    return request.META.get("REMOTE_ADDR") if request else None


def registrar(acao, request=None, usuario=None, objeto="", email_tentativa=""):
    RegistroAuditoria.objects.create(
        usuario=usuario,
        email_tentativa=email_tentativa,
        acao=acao,
        objeto=objeto,
        ip=enderecar_ip(request),
    )
