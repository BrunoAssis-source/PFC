from django import forms
from django.core.exceptions import ValidationError

from autenticacao.forms import EstiloBootstrapMixin
from catalogo.models import Operador, Variavel, normalizar

from .models import Criterio, Estudo

# Operadores que a tela de critérios oferece em cada tipo, com o rótulo do botão.
# O modelo aceita mais combinações, mas o pesquisador escolhe entre estas.
OPERADORES_DA_TELA = {
    Variavel.Tipo.NUMERICA: (
        (Operador.ENTRE, "entre"),
        (Operador.MAIOR_IGUAL, "pelo menos"),
        (Operador.MENOR_IGUAL, "no máximo"),
        (Operador.IGUAL, "exatamente"),
    ),
    Variavel.Tipo.ORDINAL: (
        (Operador.MAIOR_IGUAL, "a partir de"),
        (Operador.MENOR_IGUAL, "até"),
        (Operador.E, "exatamente"),
    ),
    Variavel.Tipo.NOMINAL: ((Operador.ESTA_EM, "está em"),),
    Variavel.Tipo.BOOLEANA: ((Operador.VERDADEIRO, "Sim"), (Operador.FALSO, "Não")),
}


class EstudoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Estudo
        fields = ("nome", "condicao", "descricao", "participantes_necessarios", "situacao")
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "participantes_necessarios": "Quantos participantes o estudo precisa reunir. Deixe em branco se ainda não houver número definido.",
        }


class CriterioForm(forms.ModelForm):
    class Meta:
        model = Criterio
        fields = ("tipo_regra", "operador", "valor_numero", "valor_numero_ate", "opcoes")
        widgets = {"opcoes": forms.CheckboxSelectMultiple}
        error_messages = {"operador": {"required": "Escolha como comparar."}}

    def __init__(self, *args, variavel, **kwargs):
        self.variavel = variavel
        super().__init__(*args, **kwargs)

        self.operadores = OPERADORES_DA_TELA[variavel.tipo]
        self.fields["operador"].choices = [(operador.value, rotulo) for operador, rotulo in self.operadores]
        if variavel.tipo == Variavel.Tipo.BOOLEANA:
            self.fields["operador"].error_messages["required"] = "Escolha sim ou não."

        if variavel.tipo != Variavel.Tipo.NUMERICA:
            del self.fields["valor_numero"], self.fields["valor_numero_ate"]
        if variavel.tipo in (Variavel.Tipo.NOMINAL, Variavel.Tipo.ORDINAL):
            self.fields["opcoes"].queryset = variavel.dominio.opcoes.all()
        else:
            del self.fields["opcoes"]

    def clean(self):
        dados = super().clean()
        # A ModelForm só copia os campos para a instância depois do clean, e a
        # validação das opções precisa deles agora.
        self.instance.variavel = self.variavel
        self.instance.operador = dados.get("operador", "")
        if "opcoes" in self.fields and "operador" in dados:
            escolhidas = list(dados.get("opcoes") or [])
            self.instance.opcoes_em_memoria = escolhidas
            try:
                self.instance.validar_opcoes()
            except ValidationError as erro:
                self.add_error(None, erro)
            else:
                self.recusar_todas_as_opcoes(dados, escolhidas)
        if not self.errors:
            self.recusar_duplicado(dados)
        return dados

    def recusar_duplicado(self, dados):
        """Mesma variável, regra, condição e valores que outro critério do estudo."""
        if not self.instance.estudo_id or "operador" not in dados:
            return
        operador = dados["operador"]
        # O segundo valor só conta no "entre"; nas outras condições ele é resíduo.
        ate = dados.get("valor_numero_ate") if operador == Operador.ENTRE else None
        escolhidas = {opcao.pk for opcao in dados.get("opcoes") or []}
        existentes = (
            Criterio.objects.filter(
                estudo_id=self.instance.estudo_id, variavel=self.variavel,
                tipo_regra=dados["tipo_regra"], operador=operador,
            )
            .exclude(pk=self.instance.pk)
            .prefetch_related("opcoes")
        )
        for existente in existentes:
            mesmo_ate = (existente.valor_numero_ate if operador == Operador.ENTRE else None) == ate
            if (
                existente.valor_numero == dados.get("valor_numero")
                and mesmo_ate
                and {opcao.pk for opcao in existente.opcoes.all()} == escolhidas
            ):
                self.add_error(None, "Este critério já existe neste estudo.")
                return

    def recusar_todas_as_opcoes(self, dados, escolhidas):
        # Um critério que cobre todas as opções não restringe ninguém: na inclusão
        # aceita todo mundo, na exclusão barra todo mundo.
        if not self.cobre_todas_as_opcoes(dados["operador"], escolhidas):
            return
        verbo = "exclui" if dados.get("tipo_regra") == Criterio.TipoRegra.EXCLUSAO else "inclui"
        self.add_error("opcoes", f"Esse critério {verbo} todos os participantes.")

    def cobre_todas_as_opcoes(self, operador, escolhidas):
        niveis = self.fields["opcoes"].queryset
        if self.variavel.tipo != Variavel.Tipo.ORDINAL:
            return operador == Operador.ESTA_EM and len(escolhidas) == niveis.count()

        # Na escala, um nível só já cobre tudo quando é "a partir do mais baixo"
        # ou "até o mais alto".
        ordem = [nivel.pk for nivel in niveis.order_by("ordem")]
        if operador == Operador.MAIOR_IGUAL:
            return escolhidas[0].pk == ordem[0]
        return operador == Operador.MENOR_IGUAL and escolhidas[0].pk == ordem[-1]

    def pendencia(self):
        for erros in self.errors.values():
            return erros[0]


class VariavelPropostaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Variavel
        fields = ("subcategoria", "nome", "tipo", "unidade", "minimo", "maximo", "dominio", "vida_util_dias", "sensivel")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Texto livre não serve de critério, e data o pesquisador não informa: a
        # idade em anos já vem do que o voluntário registrar.
        self.fields["tipo"].choices = [
            (valor, rotulo)
            for valor, rotulo in Variavel.Tipo.choices
            if valor not in (Variavel.Tipo.TEXTO, Variavel.Tipo.DATA)
        ]
        self.fields["unidade"].help_text = "Obrigatória para variável numérica."
        self.fields["vida_util_dias"].help_text = "Em branco significa permanente."

    def clean(self):
        dados = super().clean()
        nome = dados.get("nome")
        if nome:
            # O código sai do nome normalizado, para o catálogo não ganhar
            # identificadores digitados à mão e divergentes entre si.
            self.instance.codigo = normalizar(nome).replace(" ", "_")[:60]
            if Variavel.objects.filter(codigo=self.instance.codigo).exists():
                raise forms.ValidationError("Já existe uma variável com esse nome no catálogo.")
        return dados

    def parecidas(self):
        nome = self.cleaned_data.get("nome", "")
        palavras = [p for p in normalizar(nome).split() if len(p) > 3]
        if not palavras:
            return []
        consulta = Variavel.objects.none()
        for palavra in palavras:
            consulta = consulta | Variavel.objects.filter(busca__contains=palavra)
        return list(consulta.select_related("subcategoria").distinct()[:8])
