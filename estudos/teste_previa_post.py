import re
from urllib.parse import urlencode

import pytest
from django.test import Client
from django.urls import reverse

from catalogo.models import OpcaoDominio
from estudos.conftest import variavel
from estudos.models import Criterio

pytestmark = pytest.mark.django_db


def endereco_da_previa(estudo, codigo="idade_anos"):
    return reverse("estudos:previa_criterio", args=[estudo.id, variavel(codigo).id])


IDADE = {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "18"}


def test_previa_responde_a_post_com_os_dados_no_corpo(cliente, estudo):
    resposta = cliente.post(endereco_da_previa(estudo), IDADE)

    assert resposta.status_code == 200
    assert "Incluir participantes com idade de pelo menos 18 anos." in resposta.content.decode()


@pytest.mark.parametrize("metodo", ["get", "put", "delete", "patch"])
def test_previa_nao_aceita_outros_metodos(cliente, estudo, metodo):
    resposta = getattr(cliente, metodo)(endereco_da_previa(estudo))

    assert resposta.status_code == 405


def test_dados_na_query_string_sao_ignorados(cliente, estudo):
    resposta = cliente.post(endereco_da_previa(estudo) + "?" + urlencode(IDADE))

    assert 'data-completo="0"' in resposta.content.decode()


def test_previa_nao_grava_nada(cliente, estudo):
    cliente.post(endereco_da_previa(estudo), IDADE)

    assert Criterio.objects.count() == 0


def test_lista_enorme_de_municipios_cabe_no_corpo_da_requisicao(cliente, estudo):
    # Em GET, centenas de ids passariam do limite de endereço de um servidor de produção.
    municipios = list(OpcaoDominio.objects.filter(dominio__codigo="municipio", pai__valor="sp"))[:700]
    dados = {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [m.id for m in municipios]}
    assert len(urlencode(dados, doseq=True)) > 4094

    resposta = cliente.post(endereco_da_previa(estudo, "municipio_residencia"), dados)

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'data-completo="1"' in html
    assert municipios[0].rotulo.lower() in html and municipios[-1].rotulo.lower() in html


def test_previa_exige_o_token_csrf(estudo, pesquisadora):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(pesquisadora)
    pagina = cliente.get(reverse("estudos:criterios", args=[estudo.id])).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina).group(1)

    sem_token = cliente.post(endereco_da_previa(estudo), IDADE)
    com_token = cliente.post(endereco_da_previa(estudo), {**IDADE, "csrfmiddlewaretoken": token})

    assert sem_token.status_code == 403
    assert com_token.status_code == 200


def test_formulario_da_tela_leva_o_token_que_a_previa_precisa(cliente, estudo):
    html = cliente.get(reverse("estudos:configurar_criterio", args=[estudo.id, variavel("idade_anos").id])).content.decode()

    assert "csrfmiddlewaretoken" in html
    assert f'data-previa-url="{endereco_da_previa(estudo)}"' in html


def test_script_envia_a_previa_por_post_com_o_formulario_inteiro():
    from pathlib import Path

    from django.conf import settings

    script = (Path(settings.BASE_DIR) / "static" / "js" / "criterios.js").read_text(encoding="utf-8")

    assert 'method: "POST", body: new FormData(form)' in script
    assert "dados.delete" not in script
    assert 'previaUrl + "?"' not in script
