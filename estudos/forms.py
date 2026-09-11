import calendar
import datetime

from django import forms

from autenticacao.forms import EstiloBootstrapMixin
from catalogo.models import OpcaoDominio, Operador, Variavel, normalizar

from .models import Criterio, Estudo

CAMPOS_POR_TIPO = {
    Variavel.Tipo.NUMERICA: ("valor_numero", "valor_numero_ate"),
    # A data é montada por ano, mês e dia, conforme a precisão escolhida.
    Variavel.Tipo.DATA: (),
    Variavel.Tipo.NOMINAL: ("opcoes",),
    Variavel.Tipo.ORDINAL: ("opcoes",),
    Variavel.Tipo.BOOLEANA: (),
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


class CriterioForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Criterio
        fields = ("operador", "valor_numero", "valor_numero_ate", "opcoes")
        widgets = {
            "opcoes": forms.SelectMultiple(attrs={"size": 6}),
        }

    def __init__(self, *args, variavel, **kwargs):
        self.variavel = variavel
        super().__init__(*args, **kwargs)

        self.fields["operador"].choices = [
            (operador.value, operador.label) for operador in variavel.operadores
        ]

        manter = CAMPOS_POR_TIPO[variavel.tipo]
        for nome in list(self.fields):
            if nome != "operador" and nome not in manter:
                del self.fields[nome]

        if "opcoes" in self.fields:
            self.fields["opcoes"].queryset = (
                variavel.dominio.opcoes.all() if variavel.dominio_id else OpcaoDominio.objects.none()
            )
            self.fields["opcoes"].label = "Valor de referência"
            self.fields["opcoes"].help_text = "Escolha um valor."

        if variavel.tipo == Variavel.Tipo.DATA:
            self.montar_campos_de_data()

        if "valor_numero" in self.fields:
            faixa = ""
            if variavel.minimo is not None:
                faixa = f", de {variavel.minimo:.0f} a {variavel.maximo:.0f}"
            self.fields["valor_numero"].label = "Valor de referência"
            self.fields["valor_numero"].help_text = f"Em {variavel.unidade}{faixa}."

        if "valor_numero_ate" in self.fields:
            self.fields["valor_numero_ate"].label = "Segundo valor"
            self.fields["valor_numero_ate"].help_text = "Usado apenas pelo operador entre."

    def clean(self):
        dados = super().clean()
        self.instance.variavel = self.variavel
        if self.variavel.tipo == Variavel.Tipo.DATA:
            self.resolver_datas(dados)
        return dados

    def resolver_datas(self, dados):
        precisao = dados.get("precisao") or Criterio.Precisao.DIA
        self.instance.precisao = precisao
        operador = dados.get("operador")

        # Antes de recorta o começo do período, depois de recorta o fim.
        try:
            self.instance.valor_data = self.limite(dados, "", precisao, operador == Operador.DEPOIS)
            if operador == Operador.ENTRE:
                self.instance.valor_data_ate = self.limite(dados, "_ate", precisao, True)
        except forms.ValidationError as erro:
            self.add_error(None, erro)

    def montar_campos_de_data(self):
        self.fields["precisao"] = forms.ChoiceField(
            label="Precisão da data",
            choices=Criterio.Precisao.choices,
            initial=Criterio.Precisao.DIA,
        )
        for sufixo, rotulo in (("", "Data de referência"), ("_ate", "Segunda data")):
            self.fields["data" + sufixo] = forms.DateField(
                label=rotulo,
                required=False,
                widget=forms.DateInput(attrs={"type": "date"}),
            )
            self.fields["mes_ano" + sufixo] = forms.DateField(
                label=f"{rotulo}, mês e ano",
                required=False,
                input_formats=["%Y-%m"],
                widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
            )
            self.fields["ano" + sufixo] = forms.IntegerField(
                label=f"{rotulo}, ano",
                required=False,
                min_value=1900,
                max_value=2100,
                widget=forms.NumberInput(attrs={"placeholder": "aaaa"}),
            )
        for nome in ("precisao", "data", "mes_ano", "ano", "data_ate", "mes_ano_ate", "ano_ate"):
            campo = self.fields[nome]
            campo.widget.attrs["class"] = self.classe_do_widget(campo.widget)

    def limite(self, dados, sufixo, precisao, fim):
        if precisao == Criterio.Precisao.ANO:
            ano = dados.get("ano" + sufixo)
            if not ano:
                raise forms.ValidationError("Informe o ano.")
            return datetime.date(ano, 12, 31) if fim else datetime.date(ano, 1, 1)

        if precisao == Criterio.Precisao.MES:
            mes_ano = dados.get("mes_ano" + sufixo)
            if not mes_ano:
                raise forms.ValidationError("Informe o mês e o ano.")
            if not fim:
                return mes_ano.replace(day=1)
            return mes_ano.replace(day=calendar.monthrange(mes_ano.year, mes_ano.month)[1])

        data = dados.get("data" + sufixo)
        if not data:
            raise forms.ValidationError("Escolha a data no calendário.")
        return data



class VariavelPropostaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Variavel
        fields = ("subcategoria", "nome", "tipo", "unidade", "minimo", "maximo", "dominio", "vida_util_dias", "sensivel")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [
            (valor, rotulo) for valor, rotulo in Variavel.Tipo.choices if valor != Variavel.Tipo.TEXTO
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
