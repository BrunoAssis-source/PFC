import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from voluntarios import cpf

from .conftest import CPF_A, CPF_B


def test_normaliza_pontuacao():
    assert cpf.normalizar("529.982.247-25") == CPF_A


@pytest.mark.parametrize("texto", [CPF_A, CPF_B])
def test_aceita_cpf_com_digitos_corretos(texto):
    assert cpf.valido(texto)


@pytest.mark.parametrize(
    "texto",
    ["", "123", "52998224726", "52998224715", "11111111111", "00000000000", "529982247250"],
)
def test_recusa_cpf_invalido(texto):
    assert not cpf.valido(texto)


def test_mascara_esconde_os_dois_extremos():
    assert cpf.mascarar(CPF_A) == "***.982.247-**"


def test_codigo_e_deterministico_e_distingue_cpfs():
    assert cpf.codigo(CPF_A) == cpf.codigo(CPF_A)
    assert cpf.codigo(CPF_A) != cpf.codigo(CPF_B)


def test_codigo_nao_contem_o_cpf_e_tem_64_hex():
    codigo = cpf.codigo(CPF_A)
    assert len(codigo) == 64 and CPF_A not in codigo


def test_codigo_muda_com_outra_chave():
    original = cpf.codigo(CPF_A)
    with override_settings(CHAVE_HMAC="outra-chave-de-teste"):
        assert cpf.codigo(CPF_A) != original


def test_cifra_e_reversivel_e_nao_expoe_o_cpf():
    cifrado = cpf.cifrar(CPF_A)
    assert CPF_A not in cifrado
    assert cpf.decifrar(cifrado) == CPF_A


def test_cifra_nao_abre_com_outra_chave():
    cifrado = cpf.cifrar(CPF_A)
    with override_settings(CHAVE_CIFRA=Fernet.generate_key().decode()):
        with pytest.raises(Exception):
            cpf.decifrar(cifrado)
