import pytest
from django.urls import reverse

from catalogo.models import OpcaoDominio
from voluntarios.coleta import proxima_variavel
from voluntarios.models import ValorColetado

from .conftest import criterio, nova_participacao, novo_estudo


@pytest.fixture
def participacao(profissional, pesquisadora):
    estudo = novo_estudo(pesquisadora)
    criterio(estudo, "municipio_residencia", "esta_em", [OpcaoDominio.objects.filter(dominio__codigo="municipio").first()])
    return nova_participacao(profissional, estudo)


def rota(participacao, nome):
    return reverse(f"voluntarios:{nome}", args=[participacao.voluntario_id, participacao.id])


def um_estado():
    return OpcaoDominio.objects.filter(dominio__codigo="uf").order_by("ordem").first()


def test_tela_traz_estado_e_filtro_e_nao_a_lista_inteira(cliente, participacao):
    pagina = cliente.get(rota(participacao, "coleta")).content.decode()
    assert 'id="cascata-pai"' in pagina and 'id="cascata-filtro"' in pagina
    assert pagina.count("<option") < 100
    assert "cascata.js" in pagina and "coleta.js" in pagina


def test_lista_de_municipios_do_estado_vem_como_escolha_unica(cliente, participacao):
    estado = um_estado()
    resposta = cliente.get(rota(participacao, "opcoes_filhas"), {"pai": estado.id})
    esperado = OpcaoDominio.objects.filter(pai=estado).count()
    corpo = resposta.content.decode()
    assert resposta.status_code == 200
    assert corpo.count('type="radio"') == esperado and 'type="checkbox"' not in corpo


def test_so_lista_filhos_de_um_estado_do_dominio_superior(cliente, participacao):
    municipio = OpcaoDominio.objects.filter(dominio__codigo="municipio").first()
    assert cliente.get(rota(participacao, "opcoes_filhas"), {"pai": municipio.id}).status_code == 404
    assert cliente.get(rota(participacao, "opcoes_filhas"), {"pai": "abc"}).status_code == 404


def test_municipio_escolhido_na_cascata_e_gravado(cliente, participacao):
    municipio = OpcaoDominio.objects.filter(dominio__codigo="municipio").first()
    variavel = proxima_variavel(participacao)
    cliente.post(
        rota(participacao, "coleta"), {"variavel": variavel.id, "valor": municipio.id, "fonte": "voluntario"}
    )
    assert ValorColetado.objects.get().opcao == municipio


def test_envio_sem_municipio_pede_a_escolha(cliente, participacao):
    variavel = proxima_variavel(participacao)
    resposta = cliente.post(rota(participacao, "coleta"), {"variavel": variavel.id, "fonte": "voluntario"})
    assert resposta.status_code == 200
    assert "obrigatório" in resposta.content.decode()
    assert not ValorColetado.objects.exists()


def test_variavel_sem_dominio_superior_nao_usa_a_rota_de_municipios(cliente, profissional, pesquisadora):
    estudo = novo_estudo(pesquisadora)
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    participacao = nova_participacao(profissional, estudo)
    assert cliente.get(rota(participacao, "opcoes_filhas"), {"pai": um_estado().id}).status_code == 404


def test_pesquisador_nao_usa_a_rota_de_municipios(client, pesquisadora, participacao):
    client.force_login(pesquisadora)
    assert client.get(rota(participacao, "opcoes_filhas"), {"pai": um_estado().id}).status_code == 403
