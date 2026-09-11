import unicodedata

from django.core.exceptions import ValidationError
from django.db import models


def normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


class Categoria(models.Model):
    codigo = models.CharField("código", max_length=3, unique=True)
    nome = models.CharField("nome", max_length=80)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["ordem", "codigo"]

    def __str__(self):
        return f"{self.codigo} {self.nome}"


class Subcategoria(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="subcategorias")
    codigo = models.CharField("código", max_length=3)
    nome = models.CharField("nome", max_length=80)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "subcategoria"
        verbose_name_plural = "subcategorias"
        ordering = ["categoria", "ordem", "codigo"]
        constraints = [
            models.UniqueConstraint(fields=["categoria", "codigo"], name="codigo_unico_por_categoria"),
        ]

    def __str__(self):
        return f"{self.categoria.codigo}.{self.codigo} {self.nome}"


class Dominio(models.Model):
    codigo = models.SlugField("código", max_length=40, unique=True)
    nome = models.CharField("nome", max_length=80)
    ordinal = models.BooleanField("ordinal", default=False)

    class Meta:
        verbose_name = "domínio"
        verbose_name_plural = "domínios"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class OpcaoDominio(models.Model):
    dominio = models.ForeignKey(Dominio, on_delete=models.CASCADE, related_name="opcoes")
    valor = models.SlugField("valor", max_length=60)
    rotulo = models.CharField("rótulo", max_length=120)
    # Sequência usada pela comparação ordinal.
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "opção de domínio"
        verbose_name_plural = "opções de domínio"
        ordering = ["dominio", "ordem"]
        constraints = [
            models.UniqueConstraint(fields=["dominio", "valor"], name="valor_unico_por_dominio"),
        ]

    def __str__(self):
        return self.rotulo


class Operador(models.TextChoices):
    IGUAL = "igual", "="
    DIFERENTE = "diferente", "≠"
    MENOR = "menor", "<"
    MENOR_IGUAL = "menor_igual", "≤"
    MAIOR = "maior", ">"
    MAIOR_IGUAL = "maior_igual", "≥"
    ENTRE = "entre", "entre"
    E = "e", "é"
    NAO_E = "nao_e", "não é"
    ESTA_EM = "esta_em", "está em"
    NAO_ESTA_EM = "nao_esta_em", "não está em"
    VERDADEIRO = "verdadeiro", "é verdadeiro"
    FALSO = "falso", "é falso"
    ANTES = "antes", "antes de"
    DEPOIS = "depois", "depois de"


OPERADORES = {
    "numerica": (
        Operador.IGUAL, Operador.DIFERENTE, Operador.MENOR, Operador.MENOR_IGUAL,
        Operador.MAIOR, Operador.MAIOR_IGUAL, Operador.ENTRE,
    ),
    "nominal": (Operador.E, Operador.NAO_E, Operador.ESTA_EM, Operador.NAO_ESTA_EM),
    "ordinal": (
        Operador.E, Operador.NAO_E, Operador.ESTA_EM, Operador.NAO_ESTA_EM,
        Operador.MENOR_IGUAL, Operador.MAIOR_IGUAL, Operador.ENTRE,
    ),
    "booleana": (Operador.VERDADEIRO, Operador.FALSO),
    "data": (Operador.ANTES, Operador.DEPOIS, Operador.ENTRE),
    "texto": (),
}


class Variavel(models.Model):
    class Tipo(models.TextChoices):
        NUMERICA = "numerica", "numérica"
        NOMINAL = "nominal", "categórica nominal"
        ORDINAL = "ordinal", "categórica ordinal"
        BOOLEANA = "booleana", "booleana"
        DATA = "data", "data"
        TEXTO = "texto", "texto livre"

    subcategoria = models.ForeignKey(Subcategoria, on_delete=models.PROTECT, related_name="variaveis")
    codigo = models.SlugField("código", max_length=60, unique=True)
    nome = models.CharField("nome", max_length=120)
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)

    definicao = models.CharField("definição", max_length=220, blank=True)

    unidade = models.CharField("unidade canônica", max_length=30, blank=True)
    minimo = models.DecimalField("mínimo plausível", max_digits=12, decimal_places=2, null=True, blank=True)
    maximo = models.DecimalField("máximo plausível", max_digits=12, decimal_places=2, null=True, blank=True)

    dominio = models.ForeignKey(Dominio, on_delete=models.PROTECT, null=True, blank=True, related_name="variaveis")
    tabela_referencia = models.CharField("tabela de referência", max_length=40, blank=True)

    # Nulo significa permanente.
    vida_util_dias = models.PositiveIntegerField("vida útil em dias", null=True, blank=True)
    derivada = models.BooleanField("derivada", default=False)
    sensivel = models.BooleanField("sensível", default=False)
    origem = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="derivadas",
        verbose_name="calculada a partir de",
    )

    busca = models.CharField("texto de busca", max_length=200, editable=False, default="")

    class Meta:
        verbose_name = "variável"
        verbose_name_plural = "variáveis"
        ordering = ["subcategoria", "codigo"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.busca = self.texto_de_busca(self.nome, self.codigo)
        super().save(*args, **kwargs)

    @staticmethod
    def texto_de_busca(nome, codigo):
        # O código entra duas vezes, com sublinhado e com espaço, porque quem
        # digita "per capita" procura o que o código guarda como per_capita.
        return normalizar(f"{nome} {codigo} {codigo.replace('_', ' ')}")

    @property
    def operadores(self):
        return OPERADORES[self.tipo]

    def clean(self):
        if self.tipo == self.Tipo.NUMERICA:
            if not self.unidade:
                raise ValidationError({"unidade": "Variável numérica exige unidade canônica."})
            if self.minimo is None or self.maximo is None:
                raise ValidationError("Variável numérica exige faixa plausível, com mínimo e máximo.")
            if self.minimo >= self.maximo:
                raise ValidationError({"maximo": "O máximo precisa ser maior que o mínimo."})

        if self.tipo in (self.Tipo.NOMINAL, self.Tipo.ORDINAL):
            if not self.dominio_id and not self.tabela_referencia:
                raise ValidationError("Variável categórica exige domínio ou tabela de referência.")

        if self.tipo == self.Tipo.ORDINAL and self.dominio_id and not self.dominio.ordinal:
            raise ValidationError({"dominio": "Variável ordinal exige domínio marcado como ordinal."})
