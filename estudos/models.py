from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from catalogo.models import OPERADORES, Operador, Variavel


class Estudo(models.Model):
    class Situacao(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        ATIVO = "ativo", "Ativo"
        ENCERRADO = "encerrado", "Encerrado"

    nome = models.CharField("nome", max_length=150)
    condicao = models.CharField("condição estudada", max_length=120)
    descricao = models.TextField("descrição", blank=True)
    situacao = models.CharField("situação", max_length=10, choices=Situacao.choices, default=Situacao.RASCUNHO)
    participantes_necessarios = models.PositiveIntegerField("participantes necessários", null=True, blank=True)
    pesquisador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="estudos",
        verbose_name="pesquisador",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "estudo"
        verbose_name_plural = "estudos"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome

    def regras(self):
        """Critérios do estudo separados em inclusão e exclusão, já com o que a frase precisa."""
        criterios = self.criterios.select_related("variavel").prefetch_related("opcoes")
        inclusao = [c for c in criterios if c.tipo_regra == Criterio.TipoRegra.INCLUSAO]
        exclusao = [c for c in criterios if c.tipo_regra == Criterio.TipoRegra.EXCLUSAO]
        return inclusao, exclusao

    @property
    def resumo_texto(self):
        inclusao, exclusao = self.regras()
        partes = []
        for regras, abertura in ((inclusao, "Serão incluídos"), (exclusao, "Serão excluídos")):
            if regras:
                partes.append(f"{abertura} participantes com {'; '.join(c.descricao for c in regras)}.")
        return " ".join(partes)

    @property
    def resumo_criterios(self):
        inclusao = self.criterios.filter(tipo_regra=Criterio.TipoRegra.INCLUSAO).count()
        exclusao = self.criterios.count() - inclusao
        if not inclusao and not exclusao:
            return "Nenhum critério definido"
        partes = []
        if inclusao:
            partes.append(f"{inclusao} de inclusão")
        if exclusao:
            partes.append(f"{exclusao} de exclusão")
        total = inclusao + exclusao
        return f"{total} {'critério' if total == 1 else 'critérios'}: " + " e ".join(partes)


class Criterio(models.Model):
    class Precisao(models.TextChoices):
        DIA = "dia", "data completa"
        MES = "mes", "mês e ano"
        ANO = "ano", "apenas o ano"

    class TipoRegra(models.TextChoices):
        INCLUSAO = "inclusao", "Incluir"
        EXCLUSAO = "exclusao", "Excluir"

    estudo = models.ForeignKey(Estudo, on_delete=models.CASCADE, related_name="criterios")
    tipo_regra = models.CharField("regra", max_length=8, choices=TipoRegra.choices, default=TipoRegra.INCLUSAO)
    variavel = models.ForeignKey(Variavel, on_delete=models.PROTECT, related_name="criterios")
    operador = models.CharField("operador", max_length=12, choices=Operador.choices)

    valor_numero = models.DecimalField("valor", max_digits=12, decimal_places=2, null=True, blank=True)
    valor_numero_ate = models.DecimalField("até", max_digits=12, decimal_places=2, null=True, blank=True)
    valor_data = models.DateField("data", null=True, blank=True)
    valor_data_ate = models.DateField("até", null=True, blank=True)
    # Com precisão de mês ou ano, valor_data guarda o primeiro ou o último dia do período, conforme o operador.
    precisao = models.CharField("precisão da data", max_length=3, choices=Precisao.choices, default=Precisao.DIA)
    opcoes = models.ManyToManyField("catalogo.OpcaoDominio", blank=True, related_name="criterios", verbose_name="valores")

    # Valores escolhidos que ainda não foram gravados. A prévia da tela monta o
    # critério sem salvar, e o ManyToMany só existe depois do save.
    opcoes_em_memoria = None

    class Meta:
        verbose_name = "critério"
        verbose_name_plural = "critérios"
        ordering = ["tipo_regra", "variavel__codigo"]

    def __str__(self):
        return self.enunciado

    @staticmethod
    def numero(valor):
        return f"{valor.normalize():f}"

    @property
    def enunciado(self):
        rotulo = Operador(self.operador).label
        if self.operador in (Operador.VERDADEIRO, Operador.FALSO):
            return f"{self.variavel.nome} {rotulo}"
        if self.operador == Operador.ENTRE:
            if self.valor_numero is not None:
                return f"{self.variavel.nome} entre {self.numero(self.valor_numero)} e {self.numero(self.valor_numero_ate)} {self.variavel.unidade}"
            if self.valor_data is not None:
                return (
                    f"{self.variavel.nome} entre {self.data_formatada(self.valor_data)} "
                    f"e {self.data_formatada(self.valor_data_ate)}"
                )
            return f"{self.variavel.nome} entre {self.lista_de_opcoes}"
        if self.valor_numero is not None:
            return f"{self.variavel.nome} {rotulo} {self.numero(self.valor_numero)} {self.variavel.unidade}".strip()
        if self.valor_data is not None:
            return f"{self.variavel.nome} {rotulo} {self.data_formatada(self.valor_data)}"
        return f"{self.variavel.nome} {rotulo} {self.lista_de_opcoes}"

    @property
    def frase(self):
        verbo = self.TipoRegra(self.tipo_regra).label
        return f"{verbo} participantes com {self.descricao}"

    @property
    def descricao(self):
        """Variável e condição, como aparecem na lista de regras e no resumo do estudo."""
        condicao = self.condicao
        separador = "" if condicao.startswith(":") else " "
        return f"{self.variavel.rotulo.lower()}{separador}{condicao}"

    @property
    def selecionadas(self):
        if self.opcoes_em_memoria is not None:
            return self.opcoes_em_memoria
        return list(self.opcoes.all())

    @property
    def condicao(self):
        operador = self.operador
        unidade = f" {self.variavel.unidade}" if self.variavel.unidade else ""
        if operador in (Operador.VERDADEIRO, Operador.FALSO):
            return ": sim" if operador == Operador.VERDADEIRO else ": não"

        if self.valor_numero is not None:
            valor = self.numero(self.valor_numero)
            if operador == Operador.ENTRE:
                return f"entre {valor} e {self.numero(self.valor_numero_ate)}{unidade}"
            texto = {
                Operador.IGUAL: "igual a",
                Operador.DIFERENTE: "diferente de",
                Operador.MAIOR_IGUAL: "de pelo menos",
                Operador.MENOR_IGUAL: "de no máximo",
                Operador.MAIOR: "acima de",
                Operador.MENOR: "abaixo de",
            }[operador]
            return f"{texto} {valor}{unidade}"

        if self.valor_data is not None:
            inicio = self.data_formatada(self.valor_data)
            if operador == Operador.ENTRE:
                return f"entre {inicio} e {self.data_formatada(self.valor_data_ate)}"
            return f"{Operador(operador).label} {inicio}"

        rotulos = [opcao.rotulo.lower() for opcao in self.selecionadas]
        if operador == Operador.ENTRE:
            return f"entre {' e '.join(rotulos)}"
        lista = rotulos[0] if len(rotulos) == 1 else f"{', '.join(rotulos[:-1])} ou {rotulos[-1]}"
        ordinal = self.variavel.tipo == Variavel.Tipo.ORDINAL
        if operador == Operador.NAO_ESTA_EM and len(rotulos) > 1:
            lista = lista.replace(" ou ", " e ")
        return {
            Operador.E: f"igual a {lista}",
            Operador.NAO_E: f"diferente de {lista}",
            Operador.ESTA_EM: f": {lista}",
            Operador.NAO_ESTA_EM: f"diferente de {lista}",
            Operador.MAIOR_IGUAL: f"{'a partir de' if ordinal else 'de pelo menos'} {lista}",
            Operador.MENOR_IGUAL: f"{'até' if ordinal else 'de no máximo'} {lista}",
        }[operador]

    def pendencia(self):
        """Primeira mensagem que impede o critério de ser gravado, ou None se está completo."""
        try:
            self.clean()
            self.validar_opcoes()
        except ValidationError as erro:
            return erro.messages[0]
        return None

    def data_formatada(self, valor):
        if self.precisao == self.Precisao.ANO:
            return f"{valor.year}"
        if self.precisao == self.Precisao.MES:
            return f"{valor.month:02d}/{valor.year}"
        return f"{valor.day:02d}/{valor.month:02d}/{valor.year}"

    @property
    def lista_de_opcoes(self):
        return ", ".join(opcao.rotulo for opcao in self.opcoes.all())

    def clean(self):
        if self.variavel_id and self.operador not in OPERADORES[self.variavel.tipo]:
            raise ValidationError({"operador": "Este operador não vale para o tipo da variável."})

        tipo = self.variavel.tipo if self.variavel_id else None

        if tipo == Variavel.Tipo.NUMERICA:
            if self.valor_numero is None:
                raise ValidationError({"valor_numero": "Informe o valor de referência."})
            if self.operador == Operador.ENTRE:
                if self.valor_numero_ate is None:
                    raise ValidationError({"valor_numero_ate": "O operador entre exige dois valores."})
                if self.valor_numero >= self.valor_numero_ate:
                    raise ValidationError({"valor_numero_ate": "O segundo valor precisa ser maior que o primeiro."})
            self.validar_faixa()

        if tipo == Variavel.Tipo.DATA:
            # Sem campo associado porque a data vem de um dos três campos de precisão do formulário.
            if self.valor_data is None:
                raise ValidationError("Informe a data de referência.")
            if self.operador == Operador.ENTRE:
                if self.valor_data_ate is None:
                    raise ValidationError("O operador entre exige duas datas.")
                if self.valor_data >= self.valor_data_ate:
                    raise ValidationError("A segunda data precisa ser posterior à primeira.")

    def validar_faixa(self):
        variavel = self.variavel
        for valor in (self.valor_numero, self.valor_numero_ate):
            if valor is None:
                continue
            if variavel.minimo is not None and valor < variavel.minimo:
                raise ValidationError(f"O valor fica abaixo do mínimo plausível da variável, que é {variavel.minimo}.")
            if variavel.maximo is not None and valor > variavel.maximo:
                raise ValidationError(f"O valor passa do máximo plausível da variável, que é {variavel.maximo}.")

    def validar_opcoes(self):
        tipo = self.variavel.tipo
        if tipo not in (Variavel.Tipo.NOMINAL, Variavel.Tipo.ORDINAL):
            return
        quantidade = len(self.selecionadas)
        if quantidade < 1:
            raise ValidationError({"opcoes": "Escolha ao menos um valor."})
        if self.operador in (Operador.E, Operador.NAO_E, Operador.MENOR_IGUAL, Operador.MAIOR_IGUAL):
            if quantidade != 1:
                raise ValidationError({"opcoes": "Este operador aceita um valor só."})
        elif self.operador == Operador.ENTRE:
            if quantidade != 2:
                raise ValidationError({"opcoes": "O operador entre exige dois valores."})
