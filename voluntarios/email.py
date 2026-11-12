import logging

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def enviar(destinatario, assunto, template, contexto, descricao):
    """Envia pelo mesmo caminho do email de senha. Falha no envio fica no log e não interrompe a operação."""
    mensagem = EmailMultiAlternatives(assunto, render_to_string(template, contexto), to=[destinatario])
    try:
        mensagem.send()
    except Exception:
        logger.exception("Falha ao enviar o aviso: %s.", descricao)
