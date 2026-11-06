from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nome_completo, password=None, **extra_fields):
        if not email:
            raise ValueError("O email é obrigatório.")
        usuario = self.model(
            email=self.normalize_email(email),
            nome_completo=nome_completo,
            **extra_fields,
        )
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, nome_completo, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, nome_completo, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Perfil(models.TextChoices):
        PESQUISADOR = "pesquisador", "pesquisador"
        PROFISSIONAL = "profissional", "profissional"

    nome_completo = models.CharField("nome completo", max_length=150)
    email = models.EmailField("email", unique=True)
    # O padrão é o perfil de menor alcance.
    perfil = models.CharField("perfil", max_length=12, choices=Perfil.choices, default=Perfil.PROFISSIONAL)
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("equipe", default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome_completo", "perfil"]

    def __str__(self):
        return self.email

    @property
    def iniciais(self):
        partes = self.nome_completo.split()
        if not partes:
            return self.email[:2].upper()
        return (partes[0][0] + partes[-1][0]).upper() if len(partes) > 1 else partes[0][:2].upper()

    @property
    def aguarda_confirmacao(self):
        # Quem nunca entrou e está inativo ainda não confirmou o email. O administrador também pode desativar contas,
        # mas essas já tiveram login, então não caem aqui.
        return not self.is_active and self.last_login is None

    @property
    def e_pesquisador(self):
        return self.perfil == self.Perfil.PESQUISADOR

    @property
    def e_profissional(self):
        return self.perfil == self.Perfil.PROFISSIONAL


class ConfirmacaoEmail(models.Model):
    # Uma linha por usuário. Guarda só o hash do código e do segredo do link, e cada novo envio sobrescreve os anteriores.
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="confirmacao")
    codigo_hash = models.CharField(max_length=64)
    link_hash = models.CharField(max_length=64)
    enviado_em = models.DateTimeField()
    janela_inicio = models.DateTimeField()
    envios_na_janela = models.PositiveSmallIntegerField(default=0)
    tentativas = models.PositiveSmallIntegerField(default=0)
