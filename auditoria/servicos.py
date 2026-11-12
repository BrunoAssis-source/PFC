from ipaddress import ip_address

from .models import RegistroAuditoria


def enderecar_ip(request):
    if not request:
        return None

    enderecos = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    enderecos.append(request.META.get("REMOTE_ADDR", ""))
    for endereco in enderecos:
        try:
            return str(ip_address(endereco.strip()))
        except ValueError:
            continue
    return None


def registrar(acao, request=None, usuario=None, objeto="", email_tentativa=""):
    RegistroAuditoria.objects.create(
        usuario=usuario,
        email_tentativa=email_tentativa,
        acao=acao,
        objeto=objeto,
        ip=enderecar_ip(request),
    )
