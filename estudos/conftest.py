import pytest

from autenticacao.models import Usuario
from catalogo.models import OpcaoDominio, Variavel
from estudos.models import Criterio, Estudo


@pytest.fixture
def pesquisadora(db):
    return Usuario.objects.create_user(
        "p@alunos.umc.br", "Pesquisadora Teste", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )


@pytest.fixture
def estudo(pesquisadora):
    return Estudo.objects.create(nome="Controle glicêmico", condicao="Diabetes tipo 2", pesquisador=pesquisadora)


@pytest.fixture
def cliente(client, pesquisadora):
    client.force_login(pesquisadora)
    return client


def variavel(codigo):
    return Variavel.objects.get(codigo=codigo)


def opcoes(codigo_do_dominio, *valores):
    return list(
        OpcaoDominio.objects.filter(dominio__codigo=codigo_do_dominio, valor__in=valores).order_by("ordem")
    )


def gravar(estudo, codigo, operador, escolhidas=(), **campos):
    criterio = Criterio.objects.create(estudo=estudo, variavel=variavel(codigo), operador=operador, **campos)
    criterio.opcoes.set(escolhidas)
    # Os valores voltam do banco como Decimal, que é o que a tela recebe.
    criterio.refresh_from_db()
    return criterio
