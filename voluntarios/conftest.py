import pytest

from autenticacao.models import Usuario
from estudos.models import Estudo

# CPFs sintéticos que passam na conta dos dígitos verificadores.
CPF_A = "52998224725"
CPF_B = "11144477735"


@pytest.fixture
def profissional(db):
    return Usuario.objects.create_user(
        "prof@alunos.umc.br", "Profissional Teste", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL
    )


@pytest.fixture
def pesquisadora(db):
    return Usuario.objects.create_user(
        "pesq@alunos.umc.br", "Pesquisadora Teste", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )


@pytest.fixture
def estudo_ativo(pesquisadora):
    return Estudo.objects.create(
        nome="Controle glicêmico", condicao="Diabetes tipo 2", pesquisador=pesquisadora, situacao=Estudo.Situacao.ATIVO
    )


@pytest.fixture
def cliente(client, profissional):
    client.force_login(profissional)
    return client
