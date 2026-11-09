import pytest
from django.conf import settings
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from voluntarios import cpf
from voluntarios.models import Voluntario

from .conftest import CPF_A


@pytest.fixture
def voluntario(profissional):
    return Voluntario.objects.create(
        codigo_hmac=cpf.codigo(CPF_A), cpf_cifrado=cpf.cifrar(CPF_A), criado_por=profissional
    )


def rotas(voluntario):
    return [
        ("get", reverse("voluntarios:identificar")),
        ("post", reverse("voluntarios:identificar")),
        ("post", reverse("voluntarios:cadastrar")),
        ("get", reverse("voluntarios:detalhe", args=[voluntario.id])),
        ("post", reverse("voluntarios:vincular", args=[voluntario.id])),
    ]


def test_anonimo_vai_para_o_login(client, voluntario):
    for metodo, url in rotas(voluntario):
        resposta = getattr(client, metodo)(url, {"cpf": CPF_A})
        assert resposta.status_code == 302 and resposta.url.startswith(f"{reverse(settings.LOGIN_URL)}?next=")


def test_pesquisador_recebe_negativa_em_toda_rota(client, pesquisadora, voluntario):
    client.force_login(pesquisadora)
    for metodo, url in rotas(voluntario):
        assert getattr(client, metodo)(url, {"cpf": CPF_A}).status_code == 403


def test_pesquisador_nao_cria_voluntario_nem_participacao(client, pesquisadora, voluntario, estudo_ativo):
    client.force_login(pesquisadora)
    client.post(reverse("voluntarios:cadastrar"), {"cpf": "11144477735"})
    client.post(reverse("voluntarios:vincular", args=[voluntario.id]), {"estudo": estudo_ativo.id, "tcle": "on"})
    assert Voluntario.objects.count() == 1
    assert voluntario.participacoes.count() == 0


def test_negativa_fica_na_auditoria(client, pesquisadora, voluntario):
    client.force_login(pesquisadora)
    client.get(reverse("voluntarios:identificar"))
    assert RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.ACESSO_NEGADO, usuario=pesquisadora).exists()


def test_profissional_acessa(cliente, voluntario):
    assert cliente.get(reverse("voluntarios:identificar")).status_code == 200
    assert cliente.get(reverse("voluntarios:detalhe", args=[voluntario.id])).status_code == 200
