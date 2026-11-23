from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from . import limite
from .models import Usuario


AJUDA_SENHA = (
    "Use pelo menos 8 caracteres. Uma frase com três ou quatro palavras sem relação entre si, "
    "misturando letras e números, é fácil de lembrar e difícil de adivinhar. "
    "Evite senhas comuns, só números e trechos do seu nome ou email."
)


class AjudaSenhaMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("password1", "new_password1"):
            if nome in self.fields:
                self.fields[nome].help_text = AJUDA_SENHA


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

    def clean(self):
        email = self.cleaned_data.get("username", "")
        if limite.bloqueado("login", email, limite.LOGIN_MAXIMO):
            raise forms.ValidationError(
                "Muitas tentativas de entrada. Aguarde 15 minutos e tente de novo.", code="bloqueado"
            )
        try:
            resultado = super().clean()
        except forms.ValidationError:
            limite.registrar_falha("login", email)
            # O backend trata conta inativa como credencial inválida. Só avisa que falta confirmar
            # quem acertou a senha, para o aviso não revelar quais emails têm cadastro.
            usuario = Usuario.objects.filter(email__iexact=email).first()
            if usuario and usuario.aguarda_confirmacao and usuario.check_password(self.cleaned_data.get("password", "")):
                self.email_nao_confirmado = True
                self.request.session["email_confirmacao"] = usuario.email
                raise forms.ValidationError(
                    "Falta confirmar o seu email. Abra o link que enviamos no cadastro.",
                    code="email_nao_confirmado",
                )
            raise
        limite.limpar("login", email)
        return resultado


class CadastroForm(AjudaSenhaMixin, EstiloBootstrapMixin, UserCreationForm):
    # RN02: sem o aceite dos termos de uso e da política de privacidade a conta não é criada.
    aceite = forms.BooleanField(
        label="Li e aceito os termos de uso e a política de privacidade",
        error_messages={"required": "Aceite os termos de uso e a política de privacidade para criar a conta."},
    )

    class Meta:
        model = Usuario
        fields = ("nome_completo", "email", "perfil", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["aceite"].widget.attrs["class"] = "form-check-input"
        # Começa vazio para a escolha do perfil ser deliberada.
        self.fields["perfil"].choices = [("", "Selecione seu perfil")] + list(Usuario.Perfil.choices)
        self.fields["perfil"].initial = ""

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if not email.endswith("@alunos.umc.br"):
            raise forms.ValidationError("Use um email com o domínio @alunos.umc.br.")
        return email


class AceiteDosTermosForm(forms.Form):
    aceite = forms.BooleanField(
        error_messages={"required": "Aceite os termos de uso e a política de privacidade para continuar."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["aceite"].widget.attrs["class"] = "form-check-input"


class SolicitarSenhaForm(EstiloBootstrapMixin, PasswordResetForm):
    def get_users(self, email):
        # Acima do limite não envia nada, mas a tela responde igual, para não revelar quais emails têm conta.
        if limite.bloqueado("reset", email, limite.RESET_MAXIMO):
            return iter(())
        limite.registrar_falha("reset", email, limite.RESET_JANELA)
        return super().get_users(email)


class NovaSenhaForm(AjudaSenhaMixin, EstiloBootstrapMixin, SetPasswordForm):
    pass


class UsuarioEdicaoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("nome_completo", "email", "perfil", "is_active", "is_staff")
        labels = {"is_staff": "Administrador"}

    def __init__(self, *args, editando_a_si_mesmo=False, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("is_active", "is_staff"):
            self.fields[nome].widget.attrs["class"] = "form-check-input"
        # Quem edita a própria conta não pode se desativar nem tirar o próprio acesso de administrador.
        if editando_a_si_mesmo:
            del self.fields["is_active"], self.fields["is_staff"]

    def clean_email(self):
        return self.cleaned_data["email"].lower()


class TrocarSenhaForm(AjudaSenhaMixin, EstiloBootstrapMixin, PasswordChangeForm):
    pass


class MeuPerfilForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("nome_completo",)


class UsuarioCriacaoForm(AjudaSenhaMixin, EstiloBootstrapMixin, UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("nome_completo", "email", "perfil", "is_staff", "password1", "password2")
        labels = {"is_staff": "Administrador"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_staff"].widget.attrs["class"] = "form-check-input"

    def clean_email(self):
        return self.cleaned_data["email"].lower()


class ReenviarConfirmacaoForm(EstiloBootstrapMixin, forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))


class CodigoConfirmacaoForm(EstiloBootstrapMixin, forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    codigo = forms.CharField(
        label="Código recebido por email",
        max_length=12,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "placeholder": "XXXXXXXX"}),
    )
