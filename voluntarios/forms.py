from django import forms

from estudos.models import Estudo

from . import cpf as cpf_util


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
