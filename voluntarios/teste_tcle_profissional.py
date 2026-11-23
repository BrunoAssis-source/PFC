import pytest
from django.conf import settings
from django.urls import reverse

from estudos.models import Estudo, Tcle
from voluntarios import cpf
from voluntarios.models import Participacao, Voluntario

from .conftest import CPF_A, novo_estudo


@pytest.fixture
def voluntario(profissional):
    return Voluntario.objects.create(
        codigo_hmac=cpf.codigo(CPF_A), cpf_cifrado=cpf.cifrar(CPF_A), criado_por=profissional
    )


def url_tcle(estudo):
    return reverse("voluntarios:tcle_do_estudo", args=[estudo.id])


def test_profissional_abre_o_pdf_do_tcle_do_estudo_ativo(cliente, estudo_ativo):
    resposta = cliente.get(url_tcle(estudo_ativo))
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF")


def test_anonimo_vai_para_o_login(client, estudo_ativo):
    resposta = client.get(url_tcle(estudo_ativo))
    assert resposta.status_code == 302 and resposta.url.startswith(f"{reverse(settings.LOGIN_URL)}?next=")


def test_pesquisador_recebe_negativa_na_rota_do_profissional(client, pesquisadora, estudo_ativo):
    client.force_login(pesquisadora)
    assert client.get(url_tcle(estudo_ativo)).status_code == 403


def test_estudo_que_nao_esta_ativo_responde_404(cliente, estudo_ativo):
    Estudo.objects.filter(pk=estudo_ativo.pk).update(situacao=Estudo.Situacao.ENCERRADO)
    assert cliente.get(url_tcle(estudo_ativo)).status_code == 404


def test_estudo_ativo_sem_tcle_volta_com_mensagem_em_vez_de_404(cliente, estudo_ativo):
    Tcle.objects.filter(estudo=estudo_ativo).delete()
    resposta = cliente.get(url_tcle(estudo_ativo), follow=True)
    assert resposta.status_code == 200
    assert "ainda não anexou o TCLE" in resposta.content.decode()


def test_vincular_a_estudo_sem_tcle_e_recusado(cliente, voluntario, estudo_ativo):
    Tcle.objects.filter(estudo=estudo_ativo).delete()
    cliente.post(reverse("voluntarios:vincular", args=[voluntario.id]), {"estudo": estudo_ativo.id, "tcle": "on"})
    assert voluntario.participacoes.count() == 0


def test_vincular_a_estudo_com_tcle_continua_funcionando(cliente, voluntario, estudo_ativo):
    cliente.post(reverse("voluntarios:vincular", args=[voluntario.id]), {"estudo": estudo_ativo.id, "tcle": "on"})
    assert voluntario.participacoes.count() == 1


def test_detalhe_pagina_os_estudos_do_voluntario_de_dez_em_dez(cliente, profissional, pesquisadora, voluntario):
    for i in range(12):
        Participacao.objects.create(
            voluntario=voluntario, estudo=novo_estudo(pesquisadora, f"Estudo {i}"), tcle_versao="1",
            registrado_por=profissional,
        )
    url = reverse("voluntarios:detalhe", args=[voluntario.id])
    assert len(cliente.get(url).context["pagina"]) == 10
    assert len(cliente.get(url, {"pagina": 2}).context["pagina"]) == 2
