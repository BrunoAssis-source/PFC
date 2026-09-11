from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.html import escape

URL_BREVO = "https://api.brevo.com/v3/smtp/email"


class ErroBrevo(Exception):
    pass


class BackendBrevo(BaseEmailBackend):
    def __init__(self, tempo_limite=10, **kwargs):
        super().__init__(**kwargs)
        self.tempo_limite = tempo_limite

    def send_messages(self, mensagens):
        if not mensagens:
            return 0

        cabecalhos = {
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        }

        enviadas = 0
        for mensagem in mensagens:
            try:
                resposta = requests.post(
                    URL_BREVO,
                    json=self.montar_corpo(mensagem),
                    headers=cabecalhos,
                    timeout=self.tempo_limite,
                )
            except requests.RequestException:
                if not self.fail_silently:
                    raise
                continue

            if resposta.status_code >= 400:
                if self.fail_silently:
                    continue
                # O corpo traz o motivo da recusa, como IP não autorizado ou remetente não verificado.
                raise ErroBrevo(f"O Brevo recusou o envio com status {resposta.status_code}: {resposta.text}")
            enviadas += 1
        return enviadas

    def montar_corpo(self, mensagem):
        nome, endereco = parseaddr(mensagem.from_email or settings.DEFAULT_FROM_EMAIL)
        remetente = {"email": endereco}
        if nome:
            remetente["name"] = nome

        return {
            "sender": remetente,
            "to": [{"email": destino} for destino in mensagem.to],
            "subject": mensagem.subject,
            "htmlContent": self.conteudo_html(mensagem),
        }

    def conteudo_html(self, mensagem):
        for conteudo, tipo in getattr(mensagem, "alternatives", []):
            if tipo == "text/html":
                return conteudo
        # Os templates de email do projeto são texto puro. A API do Brevo
        # espera HTML, então as quebras de linha viram <br>.
        return escape(mensagem.body).replace("\n", "<br>")
