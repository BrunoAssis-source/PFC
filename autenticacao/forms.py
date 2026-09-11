from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import Usuario


class EstiloBootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = self.classe_do_widget(campo.widget)

    @staticmethod
    def classe_do_widget(widget):
        return "form-select" if isinstance(widget, forms.Select) else "form-control"

    def add_error(self, field, error):
        # Ler self.errors durante a construção dispararia a validação com os campos pela metade.
        super().add_error(field, error)
        if not field or field not in self.fields:
            return
        atributos = self.fields[field].widget.attrs
        classes = atributos.get("class", "")
        if "is-invalid" not in classes:
            atributos["class"] = f"{classes} is-invalid".strip()


class LoginForm(EstiloBootstrapMixin, AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))


class CadastroForm(EstiloBootstrapMixin, UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("nome_completo", "email", "perfil", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Começa vazio para a escolha do perfil ser deliberada.
        self.fields["perfil"].choices = [("", "Selecione seu perfil")] + list(Usuario.Perfil.choices)
        self.fields["perfil"].initial = ""

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if not email.endswith("@alunos.umc.br"):
            raise forms.ValidationError("Use um email com o domínio @alunos.umc.br.")
        return email


class SolicitarSenhaForm(EstiloBootstrapMixin, PasswordResetForm):
    pass


class NovaSenhaForm(EstiloBootstrapMixin, SetPasswordForm):
    pass
