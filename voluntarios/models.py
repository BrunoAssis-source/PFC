from django.conf import settings
from django.db import models

from estudos.models import Estudo

# Versão do texto do TCLE que o profissional confere no documento físico. Muda quando o termo do comitê mudar.
TCLE_VERSAO_ATUAL = "1"


class Voluntario(models.Model):
    # Só a identificação. As variáveis de pesquisa se ligam ao voluntário por codigo_hmac, nunca pelo CPF.
    codigo_hmac = models.CharField("código", max_length=64, unique=True)
    cpf_cifrado = models.TextField("CPF cifrado")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="cadastrado por"
    )

    class Meta:
        verbose_name = "voluntário"
        verbose_name_plural = "voluntários"

    def __str__(self):
        return self.codigo_hmac[:8]


class Participacao(models.Model):
    class Situacao(models.TextChoices):
        EM_COLETA = "em_coleta", "em coleta"
        INTERROMPIDA = "interrompida", "interrompida"
        CONCLUIDA = "concluida", "concluída"
        REVOGADA = "revogada", "revogada"

    voluntario = models.ForeignKey(Voluntario, on_delete=models.PROTECT, related_name="participacoes")
    estudo = models.ForeignKey(Estudo, on_delete=models.PROTECT, related_name="participacoes")
    situacao = models.CharField("situação", max_length=12, choices=Situacao.choices, default=Situacao.EM_COLETA)
    tcle_versao = models.CharField("versão do TCLE", max_length=10)
    tcle_aceito_em = models.DateTimeField("TCLE aceito em", auto_now_add=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="registrado por"
    )

    class Meta:
        verbose_name = "participação"
        verbose_name_plural = "participações"
        constraints = [models.UniqueConstraint(fields=["voluntario", "estudo"], name="participacao_unica")]
