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
        USUARIO_EDICAO = "usuario_edicao", "edição de usuário"
        USUARIO_EXCLUSAO = "usuario_exclusao", "exclusão de usuário"
        CRITERIO_ADICAO = "criterio_adicao", "adição de critério"
        CRITERIO_EDICAO = "criterio_edicao", "edição de critério"
        CRITERIO_REMOCAO = "criterio_remocao", "remoção de critério"
        VOLUNTARIO_BUSCA = "voluntario_busca", "busca de voluntário"
        VOLUNTARIO_CADASTRO = "voluntario_cadastro", "cadastro de voluntário"
        VOLUNTARIO_DUPLICADO = "voluntario_duplicado", "cadastro de voluntário repetido"
        VOLUNTARIO_LEITURA = "voluntario_leitura", "leitura de voluntário"
        PARTICIPACAO_VINCULO = "participacao_vinculo", "vínculo a estudo com TCLE"
        COLETA_RESPOSTA = "coleta_resposta", "resposta de coleta"
        SENSIVEL_RESPOSTA = "sensivel_resposta", "resposta a variável sensível"
        COLETA_ELIMINACAO = "coleta_eliminacao", "coleta encerrada por critério"
        PENDENCIAS_CONSULTA = "pendencias_consulta", "consulta às pendências"
        PENDENCIA_COLETA = "pendencia_coleta", "coleta de valores faltantes"

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
    # Texto sem limite porque a edição de critério guarda a frase antes e depois.
    objeto = models.TextField("objeto", blank=True)
    ip = models.GenericIPAddressField("endereço IP", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-criado_em"]

    def __str__(self):
        quem = self.usuario or self.email_tentativa or "anônimo"
        return f"{self.get_acao_display()} - {quem}"
