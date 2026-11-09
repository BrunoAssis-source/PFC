import csv

import pytest

from catalogo.busca import buscar_criterios, selecionaveis
from catalogo.models import OpcaoDominio, Variavel
from catalogo.migrations import __path__ as pasta_das_migracoes
from pathlib import Path

pytestmark = pytest.mark.django_db

DADOS = Path(pasta_das_migracoes[0]).parent / "dados"


def municipios():
    return OpcaoDominio.objects.filter(dominio__codigo="municipio")


def test_os_27_estados_estao_carregados():
    assert OpcaoDominio.objects.filter(dominio__codigo="uf").count() == 27


def test_todos_os_municipios_do_arquivo_do_ibge_estao_carregados():
    with open(DADOS / "municipios_ibge.csv", encoding="utf-8", newline="") as f:
        esperados = {linha["codigo"] for linha in csv.DictReader(f, delimiter=";")}

    assert set(municipios().values_list("valor", flat=True)) == esperados
    assert len(esperados) > 5500


@pytest.mark.parametrize("sigla, total", [("SP", 645), ("MG", 853), ("RJ", 92), ("DF", 1)])
def test_quantidade_de_municipios_por_estado(sigla, total):
    assert municipios().filter(pai__valor=sigla.lower()).count() == total


def test_todo_municipio_pertence_a_um_estado():
    assert not municipios().filter(pai__isnull=True).exists()
    assert not municipios().exclude(pai__dominio__codigo="uf").exists()


def test_municipio_traz_o_codigo_do_ibge_e_a_sigla_no_rotulo():
    mogi = municipios().get(valor="3530607")

    assert mogi.rotulo == "Mogi das Cruzes (SP)"
    assert mogi.pai.rotulo == "São Paulo"


def test_nomes_repetidos_em_estados_diferentes_ficam_distintos():
    rotulos = list(municipios().values_list("rotulo", flat=True))

    assert len(rotulos) == len(set(rotulos))


def test_dominio_de_municipio_tem_o_estado_como_superior():
    variavel = Variavel.objects.get(codigo="municipio_residencia")

    assert variavel.dominio.superior.codigo == "uf"


def test_municipio_e_estado_podem_ser_criterio():
    assert {"Município de residência", "Estado de residência"} <= {v.rotulo for v in selecionaveis()}


def test_estado_e_perguntado_direto_e_nao_derivado_do_municipio():
    estado = Variavel.objects.get(codigo="uf_residencia")

    assert not estado.derivada
    assert not estado.origem.exists()


@pytest.mark.parametrize(
    "termo, rotulo",
    [("cidade", "Município de residência"), ("onde mora", "Município de residência"), ("uf", "Estado de residência")],
)
def test_busca_acha_municipio_e_estado_por_sinonimo(termo, rotulo):
    assert rotulo in [v.rotulo for v in buscar_criterios(termo)]
