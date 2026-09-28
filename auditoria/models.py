from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    class Acao(models.TextChoices):
        LOGIN_SUCESSO = "login_sucesso", "login com sucesso"
        LOGIN_FALHA = "login_falha", "login com falha"
        LOGOUT = "logout", "logout"
        CADASTRO = "cadastro", "criação de conta"
        SENHA_REDEFINIDA = "senha_redefinida", "senha redefinida"
        ACESSO_NEGADO = "acesso_negado", "acesso negado por perfil"
        ESTUDO_LEITURA = "estudo_leitura", "leitura de estudo"
        ESTUDO_EDICAO = "estudo_edicao", "edição de estudo"

    # Nulo quando o login falhou antes de identificar um usuário válido.
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
        verbose_name="usuário",
    )
    email_tentativa = models.EmailField("email informado", blank=True)
    acao = models.CharField("ação", max_length=20, choices=Acao.choices)
    objeto = models.CharField("objeto", max_length=150, blank=True)
    ip = models.GenericIPAddressField("endereço IP", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em"]

    def __str__(self):
        quem = self.usuario or self.email_tentativa or "anônimo"
        return f"{self.get_acao_display()} - {quem}"
