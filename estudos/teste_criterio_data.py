from datetime import date

import pytest
from django.urls import reverse

from estudos.conftest import variavel
from estudos.models import Criterio

pytestmark = pytest.mark.django_db


def adicionar(cliente, estudo, **dados):
    corpo = {"tipo_regra": "inclusao", **dados}
    return cliente.post(reverse("estudos:adicionar_criterio", args=[estudo.id, variavel("data_nascimento").id]), corpo)


def unico():
    return Criterio.objects.get()


def test_RF06_CA02_depois_de_com_precisao_de_ano_grava_o_ultimo_dia_e_exibe_o_ano(cliente, estudo):
    resposta = adicionar(cliente, estudo, operador="depois", precisao="ano", ano="1990")

    assert resposta.status_code == 200
    criterio = unico()
    assert criterio.valor_data == date(1990, 12, 31)
    assert criterio.precisao == Criterio.Precisao.ANO
    assert "Data de nascimento depois de 1990" in resposta.content.decode()


def test_RN17_antes_de_usa_o_primeiro_dia_do_periodo(cliente, estudo):
    adicionar(cliente, estudo, operador="antes", precisao="ano", ano="1990")
    assert unico().valor_data == date(1990, 1, 1)


def test_RN17_precisao_de_mes_usa_o_primeiro_ou_o_ultimo_dia_do_mes(cliente, estudo):
    adicionar(cliente, estudo, operador="antes", precisao="mes", ano="1990", mes="2")
    assert unico().valor_data == date(1990, 2, 1)
    Criterio.objects.all().delete()

    resposta = adicionar(cliente, estudo, operador="depois", precisao="mes", ano="1992", mes="2")
    assert unico().valor_data == date(1992, 2, 29)
    assert "Data de nascimento depois de 02/1992" in resposta.content.decode()


def test_RN17_precisao_de_dia_guarda_a_propria_data(cliente, estudo):
    resposta = adicionar(cliente, estudo, operador="antes", precisao="dia", ano="1990", mes="5", dia="10")
    assert unico().valor_data == date(1990, 5, 10)
    assert "Data de nascimento antes de 10/05/1990" in resposta.content.decode()


def test_RN15_entre_vai_do_primeiro_dia_do_inicio_ao_ultimo_dia_do_fim(cliente, estudo):
    resposta = adicionar(cliente, estudo, operador="entre", precisao="ano", ano="1980", ano_ate="1990")
    criterio = unico()
    assert (criterio.valor_data, criterio.valor_data_ate) == (date(1980, 1, 1), date(1990, 12, 31))
    assert "Data de nascimento entre 1980 e 1990" in resposta.content.decode()


def test_RN15_tela_oferece_so_os_operadores_de_data(cliente, estudo):
    pagina = cliente.get(
        reverse("estudos:configurar_criterio", args=[estudo.id, variavel("data_nascimento").id])
    ).content.decode()
    for valor in ("antes", "depois", "entre"):
        assert f'name="operador" value="{valor}"' in pagina
    assert 'value="maior_igual"' not in pagina and 'value="igual"' not in pagina
    for valor in ("dia", "mes", "ano"):
        assert f'name="precisao" value="{valor}"' in pagina


@pytest.mark.parametrize(
    "dados",
    [
        {"operador": "antes", "precisao": "ano"},
        {"operador": "antes", "precisao": "mes", "ano": "1990"},
        {"operador": "antes", "precisao": "dia", "ano": "1990", "mes": "5"},
        {"operador": "antes", "precisao": "dia", "ano": "1990", "mes": "2", "dia": "31"},
        {"operador": "antes", "precisao": "ano", "ano": "1800"},
        {"operador": "entre", "precisao": "ano", "ano": "1990"},
        {"operador": "entre", "precisao": "ano", "ano": "1990", "ano_ate": "1980"},
    ],
)
def test_data_incompleta_ou_invalida_nao_e_gravada(cliente, estudo, dados):
    resposta = adicionar(cliente, estudo, **dados)
    assert resposta.status_code == 422
    assert not Criterio.objects.exists()


def test_operador_numerico_nao_vale_para_data(cliente, estudo):
    assert adicionar(cliente, estudo, operador="maior_igual", precisao="ano", ano="1990").status_code == 422


def test_editar_criterio_de_data_abre_com_os_valores_gravados(cliente, estudo):
    adicionar(cliente, estudo, operador="entre", precisao="mes", ano="1980", mes="3", ano_ate="1990", mes_ate="7")
    criterio = unico()
    pagina = cliente.get(reverse("estudos:editar_criterio", args=[estudo.id, criterio.id])).content.decode()
    assert 'name="ano" min="1900" max="2100" inputmode="numeric" value="1980"' in pagina
    assert 'name="mes_ate" min="1" max="12" inputmode="numeric" value="7"' in pagina
    assert 'name="precisao" value="mes" checked' in pagina

    resposta = cliente.post(
        reverse("estudos:editar_criterio", args=[estudo.id, criterio.id]),
        {"tipo_regra": "inclusao", "operador": "entre", "precisao": "mes", "ano": "1981", "mes": "3",
         "ano_ate": "1990", "mes_ate": "7"},
    )
    criterio.refresh_from_db()
    assert resposta.status_code == 200
    assert criterio.valor_data == date(1981, 3, 1)


def test_data_de_nascimento_aparece_no_seletor(cliente, estudo):
    busca = cliente.get(reverse("estudos:buscar_variaveis", args=[estudo.id]), {"q": "nascimento"}).content.decode()
    assert "Data de nascimento" in busca
