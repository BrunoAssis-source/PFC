from django import forms

from catalogo.models import Variavel
from estudos.models import Estudo

from . import cpf as cpf_util
from .models import ValorBase


class CpfForm(forms.Form):
    cpf = forms.CharField(
        label="CPF do voluntário",
        max_length=14,
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric", "autocomplete": "off"}),
    )

    def clean_cpf(self):
        numeros = cpf_util.normalizar(self.cleaned_data["cpf"])
        if not cpf_util.valido(numeros):
            raise forms.ValidationError("CPF inválido. Confira os 11 dígitos.")
        return numeros


class VinculoForm(forms.Form):
    estudo = forms.ModelChoiceField(
        label="Estudo",
        queryset=Estudo.objects.filter(situacao=Estudo.Situacao.ATIVO),
        empty_label="Escolha um estudo ativo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    tcle = forms.BooleanField(
        label="Conferi o TCLE assinado pelo voluntário, no documento físico",
        error_messages={"required": "Sem o TCLE assinado não há participação."},
    )


class RespostaForm(forms.Form):
    fonte = forms.ChoiceField(
        label="Fonte da informação",
        choices=ValorBase.Fonte.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, variavel, **kwargs):
        super().__init__(*args, **kwargs)
        self.variavel = variavel
        tipo = variavel.tipo
        rotulo = variavel.nome
        if tipo == Variavel.Tipo.NUMERICA:
            self.fields["valor"] = forms.DecimalField(
                label=rotulo,
                min_value=variavel.minimo,
                max_value=variavel.maximo,
                decimal_places=2,
                widget=forms.NumberInput(attrs={"class": "form-control", "step": "any"}),
                help_text=f"Valor {variavel.faixa}." if variavel.faixa else "",
            )
        elif tipo in (Variavel.Tipo.NOMINAL, Variavel.Tipo.ORDINAL):
            self.fields["valor"] = forms.ModelChoiceField(
                label=rotulo,
                queryset=variavel.dominio.opcoes.all(),
                empty_label="Escolha uma opção",
                widget=forms.Select(attrs={"class": "form-select"}),
            )
        elif tipo == Variavel.Tipo.BOOLEANA:
            self.fields["valor"] = forms.ChoiceField(
                label=rotulo, choices=[("sim", "Sim"), ("nao", "Não")], widget=forms.RadioSelect
            )
        else:
            self.fields["valor"] = forms.DateField(
                label=rotulo, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
            )
        self.order_fields(["valor", "fonte"])

    def valores(self):
        valor = self.cleaned_data["valor"]
        tipo = self.variavel.tipo
        if tipo == Variavel.Tipo.NUMERICA:
            return {"valor_numero": valor}
        if tipo == Variavel.Tipo.BOOLEANA:
            return {"valor_booleano": valor == "sim"}
        if tipo == Variavel.Tipo.DATA:
            return {"valor_data": valor}
        return {"opcao": valor}
