from django.conf import settings
from django.db import models

from catalogo.models import OpcaoDominio, Variavel
from estudos.models import Criterio, Estudo

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
        ELIMINADA = "eliminada", "eliminada"
        INTERROMPIDA = "interrompida", "interrompida"
        CONCLUIDA = "concluida", "concluída"
        REVOGADA = "revogada", "revogada"

    class Origem(models.TextChoices):
        COLETADO = "coletado", "coletado neste estudo"
        REAPROVEITADO = "reaproveitado", "dados reaproveitados"

    voluntario = models.ForeignKey(Voluntario, on_delete=models.PROTECT, related_name="participacoes")
    estudo = models.ForeignKey(Estudo, on_delete=models.PROTECT, related_name="participacoes")
    situacao = models.CharField("situação", max_length=12, choices=Situacao.choices, default=Situacao.EM_COLETA)
    tcle_versao = models.CharField("versão do TCLE", max_length=10)
    tcle_aceito_em = models.DateTimeField("TCLE aceito em", auto_now_add=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="registrado por"
    )
    # Só o pesquisador vê o critério que eliminou. A tela do profissional não lê estes dois campos.
    criterio_reprovado = models.ForeignKey(
        Criterio, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="critério reprovado"
    )
    encerrada_em = models.DateTimeField("encerrada em", null=True, blank=True)
    # Reaproveitado é o vínculo criado pela inclusão do pesquisador com dados de outro estudo, sem coleta nem novo TCLE.
    origem = models.CharField("origem", max_length=13, choices=Origem.choices, default=Origem.COLETADO)

    class Meta:
        verbose_name = "participação"
        verbose_name_plural = "participações"
        constraints = [models.UniqueConstraint(fields=["voluntario", "estudo"], name="participacao_unica")]


class RegistroAnonimo(models.Model):
    # Resto de uma participação cujo voluntário teve os dados eliminados. Sem código nem chave estrangeira para o
    # voluntário, só o que o painel do pesquisador precisa para continuar contando.
    estudo = models.ForeignKey(Estudo, on_delete=models.PROTECT, related_name="registros_anonimos")
    situacao = models.CharField("situação", max_length=12, choices=Participacao.Situacao.choices)
    incluido = models.BooleanField("incluído pelo pesquisador", default=False)
    criterio_reprovado = models.ForeignKey(
        Criterio, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="critério reprovado"
    )
    entrou_em = models.DateTimeField("entrou em")

    class Meta:
        verbose_name = "registro anônimo"
        verbose_name_plural = "registros anônimos"



class DecisaoCandidato(models.Model):
    # Uma linha por estudo e voluntário. Liga pelo código HMAC, sem chave estrangeira, para sobreviver à eliminação
    # dos dados pessoais do voluntário. A decisão anterior fica na auditoria.
    class Decisao(models.TextChoices):
        INCLUIDO = "incluido", "incluído"
        RECUSADO = "recusado", "recusado"

    estudo = models.ForeignKey(Estudo, on_delete=models.PROTECT, related_name="decisoes")
    codigo_voluntario = models.CharField("código do voluntário", max_length=64)
    decisao = models.CharField("decisão", max_length=8, choices=Decisao.choices)
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decidido_em = models.DateTimeField("decidido em")
    # Classificação sugerida no momento da decisão, que muda depois com os dados.
    classificacao_na_decisao = models.CharField("classificação na decisão", max_length=10)

    class Meta:
        verbose_name = "decisão sobre candidato"
        verbose_name_plural = "decisões sobre candidatos"
        constraints = [models.UniqueConstraint(fields=["estudo", "codigo_voluntario"], name="decisao_unica")]


class PendenciaNotificada(models.Model):
    # Guarda o que já foi avisado, para o email sair quando a pendência surge e não a cada consulta.
    voluntario = models.ForeignKey(Voluntario, on_delete=models.CASCADE, related_name="+")
    estudo = models.ForeignKey(Estudo, on_delete=models.CASCADE, related_name="+")
    notificada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["voluntario", "estudo"], name="pendencia_notificada_unica")]


class ValorBase(models.Model):
    # Uma linha por valor coletado. O voluntário entra só pelo código HMAC, sem chave estrangeira para o CPF.
    class Fonte(models.TextChoices):
        VOLUNTARIO = "voluntario", "informado pelo voluntário"
        DOCUMENTO = "documento", "documento apresentado"
        PRONTUARIO = "prontuario", "prontuário ou registro de saúde"

    codigo_voluntario = models.CharField("código do voluntário", max_length=64, db_index=True)
    variavel = models.ForeignKey(Variavel, on_delete=models.PROTECT, related_name="+")
    valor_numero = models.DecimalField("valor", max_digits=12, decimal_places=2, null=True, blank=True)
    valor_data = models.DateField("data", null=True, blank=True)
    opcao = models.ForeignKey(OpcaoDominio, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    valor_booleano = models.BooleanField("sim ou não", null=True, blank=True)
    fonte = models.CharField("fonte", max_length=12, choices=Fonte.choices)
    participacao = models.ForeignKey(Participacao, on_delete=models.PROTECT, related_name="+")
    coletado_em = models.DateTimeField("coletado em", auto_now_add=True)
    coletado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True


class ValorColetado(ValorBase):
    class Meta:
        verbose_name = "valor coletado"
        verbose_name_plural = "valores coletados"


class ValorSensivel(ValorBase):
    # Mesma estrutura em tabela separada. Sem cifra de coluna, porque a verificação compara no banco.
    class Meta:
        verbose_name = "valor sensível"
        verbose_name_plural = "valores sensíveis"
