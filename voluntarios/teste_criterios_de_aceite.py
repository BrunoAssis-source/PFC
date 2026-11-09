from django.urls import reverse

from voluntarios import cpf
from voluntarios.models import Voluntario

from .conftest import CPF_A


def test_RF08_CA01_cpf_ja_cadastrado_abre_o_cadastro_existente_sem_criar_outro(cliente, profissional):
    existente = Voluntario.objects.create(
        codigo_hmac=cpf.codigo(CPF_A), cpf_cifrado=cpf.cifrar(CPF_A), criado_por=profissional
    )

    resposta = cliente.post(reverse("voluntarios:identificar"), {"cpf": "529.982.247-25"})

    assert resposta.status_code == 302
    assert resposta.url == reverse("voluntarios:detalhe", args=[existente.id])
    assert Voluntario.objects.count() == 1


def test_RF08_CA02_cpf_com_digito_verificador_invalido_e_recusado(cliente):
    for invalido in ("52998224726", "529.982.247-24", "11111111111"):
        identificar = cliente.post(reverse("voluntarios:identificar"), {"cpf": invalido})
        cadastrar = cliente.post(reverse("voluntarios:cadastrar"), {"cpf": invalido})

        assert identificar.status_code == 200 and "CPF inválido" in identificar.content.decode()
        assert cadastrar.status_code == 302 and cadastrar.url == reverse("voluntarios:identificar")
    assert not Voluntario.objects.exists()


def test_RF08_RN21_cpf_fica_cifrado_e_o_codigo_localiza_sem_decifrar(cliente, profissional):
    cliente.post(reverse("voluntarios:cadastrar"), {"cpf": CPF_A})

    voluntario = Voluntario.objects.get(codigo_hmac=cpf.codigo(CPF_A))
    assert CPF_A not in voluntario.cpf_cifrado
    assert cpf.decifrar(voluntario.cpf_cifrado) == CPF_A


def test_RF08_RN22_mesmo_cpf_nao_gera_dois_cadastros(cliente):
    cliente.post(reverse("voluntarios:cadastrar"), {"cpf": CPF_A})
    cliente.post(reverse("voluntarios:cadastrar"), {"cpf": "529.982.247-25"})

    assert Voluntario.objects.count() == 1
