import pytest
from django.urls import reverse

from autenticacao.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def profissional():
    return Usuario.objects.create_user(
        "prof@alunos.umc.br", "Nome Antigo", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL
    )


def test_pessoa_altera_apenas_o_proprio_nome(client, profissional):
    client.force_login(profissional)

    resposta = client.post(
        reverse("meu_perfil"),
        {
            "nome_completo": "Nome Novo",
            "email": "outro@alunos.umc.br",
            "perfil": Usuario.Perfil.PESQUISADOR,
            "is_staff": "on",
            "is_superuser": "on",
            "is_active": "",
        },
    )

    profissional.refresh_from_db()
    assert resposta.status_code == 302
    assert profissional.nome_completo == "Nome Novo"
    assert profissional.email == "prof@alunos.umc.br"
    assert profissional.perfil == Usuario.Perfil.PROFISSIONAL
    assert not profissional.is_staff
    assert not profissional.is_superuser
    assert profissional.is_active


def test_anonimo_vai_para_o_login(client):
    resposta = client.get(reverse("meu_perfil"))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
