import hmac
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import ConfirmacaoEmail

INTERVALO_ENVIO = timedelta(seconds=60)
JANELA_ENVIOS = timedelta(hours=1)
MAX_ENVIOS_JANELA = 5
MAX_TENTATIVAS = 5
VALIDADE_CODIGO = timedelta(minutes=30)
VALIDADE_LINK = timedelta(days=3)
ALFABETO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


class LimiteDeEnvio(Exception):
    pass


def _resumo(valor):
    return salted_hmac("autenticacao.confirmacao", valor).hexdigest()


def emitir(usuario):
    agora = timezone.now()
    with transaction.atomic():
        # A linha é criada antes do bloqueio porque select_for_update não trava o que ainda não existe.
        ConfirmacaoEmail.objects.get_or_create(
            usuario=usuario,
            defaults={
                "codigo_hash": "",
                "link_hash": "",
                "enviado_em": agora - INTERVALO_ENVIO,
                "janela_inicio": agora,
            },
        )
        registro = ConfirmacaoEmail.objects.select_for_update().get(usuario=usuario)
        if agora - registro.enviado_em < INTERVALO_ENVIO:
            raise LimiteDeEnvio
        if agora - registro.janela_inicio >= JANELA_ENVIOS:
            registro.janela_inicio, registro.envios_na_janela = agora, 0
        if registro.envios_na_janela >= MAX_ENVIOS_JANELA:
            raise LimiteDeEnvio

        codigo = "".join(secrets.choice(ALFABETO) for _ in range(8))
        segredo = secrets.token_urlsafe(24)
        registro.codigo_hash = _resumo(codigo)
        registro.link_hash = _resumo(segredo)
        registro.enviado_em = agora
        registro.tentativas = 0
        registro.envios_na_janela += 1
        registro.save()
    return codigo, segredo


def validar_codigo(usuario, informado):
    informado = informado.upper().replace("-", "").replace(" ", "").replace("0", "O").replace("1", "I")
    registro = ConfirmacaoEmail.objects.filter(usuario=usuario).first()
    if registro is None or timezone.now() - registro.enviado_em > VALIDADE_CODIGO:
        return False
    if registro.tentativas >= MAX_TENTATIVAS:
        return False
    if hmac.compare_digest(registro.codigo_hash, _resumo(informado)):
        return True
    ConfirmacaoEmail.objects.filter(pk=registro.pk).update(tentativas=F("tentativas") + 1)
    return False


def validar_link(usuario, segredo):
    registro = ConfirmacaoEmail.objects.filter(usuario=usuario).first()
    if registro is None or timezone.now() - registro.enviado_em > VALIDADE_LINK:
        return False
    return hmac.compare_digest(registro.link_hash, _resumo(segredo))


def encerrar(usuario):
    ConfirmacaoEmail.objects.filter(usuario=usuario).delete()
