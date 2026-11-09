import pytest

from autenticacao.models import Usuario
from catalogo.models import OpcaoDominio, Variavel
from estudos.models import Criterio, Estudo
from voluntarios import cpf
from voluntarios.models import Participacao, Voluntario

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


def variavel(codigo):
    return Variavel.objects.get(codigo=codigo)


def opcoes(dominio, *valores):
    return list(OpcaoDominio.objects.filter(dominio__codigo=dominio, valor__in=valores).order_by("ordem"))


def criterio(estudo, codigo, operador, escolhidas=(), tipo_regra=Criterio.TipoRegra.INCLUSAO, **campos):
    novo = Criterio.objects.create(
        estudo=estudo, variavel=variavel(codigo), operador=operador, tipo_regra=tipo_regra, **campos
    )
    novo.opcoes.set(escolhidas)
    return novo


def novo_estudo(pesquisadora, nome="Estudo de teste"):
    return Estudo.objects.create(
        nome=nome, condicao="Condição", pesquisador=pesquisadora, situacao=Estudo.Situacao.ATIVO
    )


def nova_participacao(profissional, estudo, numero=CPF_A):
    voluntario, _ = Voluntario.objects.get_or_create(
        codigo_hmac=cpf.codigo(numero),
        defaults={"cpf_cifrado": cpf.cifrar(numero), "criado_por": profissional},
    )
    return Participacao.objects.create(
        voluntario=voluntario, estudo=estudo, tcle_versao="1", registrado_por=profissional
    )
