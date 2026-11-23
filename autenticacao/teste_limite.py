import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse

from .models import Usuario

SENHA = "Senha!2026x"


@pytest.fixture(autouse=True)
def cache_limpo(db):
    cache.clear()


@pytest.fixture
def usuario(db):
    return Usuario.objects.create_user("u@alunos.umc.br", "U", SENHA, perfil=Usuario.Perfil.PESQUISADOR)


def entrar(client, email, senha):
    return client.post(reverse("login"), {"username": email, "password": senha})


def test_login_bloqueia_apos_cinco_falhas_mesmo_com_senha_certa(client, usuario):
    for _ in range(5):
        entrar(client, usuario.email, "errada")
    resposta = entrar(client, usuario.email, SENHA)
    assert resposta.status_code == 200 and "Muitas tentativas" in resposta.content.decode()


def test_login_com_quatro_falhas_ainda_entra_e_zera_o_contador(client, usuario):
    for _ in range(4):
        entrar(client, usuario.email, "errada")
    assert entrar(client, usuario.email, SENHA).status_code == 302
    client.logout()
    for _ in range(4):
        entrar(client, usuario.email, "errada")
    assert entrar(client, usuario.email, SENHA).status_code == 302


def test_bloqueio_de_um_email_nao_afeta_outro(client, usuario):
    outro = Usuario.objects.create_user("o@alunos.umc.br", "O", SENHA, perfil=Usuario.Perfil.PESQUISADOR)
    for _ in range(6):
        entrar(client, usuario.email, "errada")
    assert entrar(client, outro.email, SENHA).status_code == 302


def test_bloqueio_vale_tambem_para_email_inexistente(client, usuario):
    for _ in range(5):
        entrar(client, "ninguem@alunos.umc.br", "x")
    assert "Muitas tentativas" in entrar(client, "ninguem@alunos.umc.br", "x").content.decode()


def test_email_invalido_nao_gera_bloqueio_compartilhado(client, usuario):
    for _ in range(10):
        entrar(client, "isso-nao-e-email", "x")
    assert entrar(client, usuario.email, SENHA).status_code == 302


def test_reset_de_senha_limita_os_emails_e_responde_igual(client, usuario):
    mail.outbox.clear()
    destinos = [client.post(reverse("senha_reset"), {"email": usuario.email})["Location"] for _ in range(6)]
    assert len(mail.outbox) == 3
    assert len(set(destinos)) == 1
