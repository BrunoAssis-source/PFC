import pytest
from django.urls import reverse

from estudos.conftest import gravar, variavel
from estudos.models import Criterio, Estudo

pytestmark = pytest.mark.django_db


def endereco(nome, estudo, *args):
    return reverse(f"estudos:{nome}", args=[estudo.id, *args])


@pytest.fixture
def encerrado(estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    estudo.situacao = Estudo.Situacao.ENCERRADO
    estudo.save()
    return estudo, criterio


def test_RN20_servidor_recusa_incluir_criterio_em_estudo_encerrado(cliente, encerrado):
    estudo, _ = encerrado
    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, variavel("numero_filhos").id),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "1"},
    )
    assert resposta.status_code == 403
    assert Criterio.objects.count() == 1


def test_RN20_servidor_recusa_alterar_criterio_em_estudo_encerrado(cliente, encerrado):
    estudo, criterio = encerrado
    abrir = cliente.get(endereco("editar_criterio", estudo, criterio.id))
    salvar = cliente.post(
        endereco("editar_criterio", estudo, criterio.id),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "21"},
    )
    criterio.refresh_from_db()
    assert abrir.status_code == 403 and salvar.status_code == 403
    assert criterio.valor_numero == 18


def test_RN20_servidor_recusa_remover_criterio_em_estudo_encerrado(cliente, encerrado):
    estudo, criterio = encerrado
    resposta = cliente.post(endereco("remover_criterio", estudo, criterio.id))
    assert resposta.status_code == 403
    assert Criterio.objects.filter(pk=criterio.pk).exists()


def test_RN20_formulario_e_previa_tambem_sao_recusados(cliente, encerrado):
    estudo, _ = encerrado
    variavel_id = variavel("numero_filhos").id
    assert cliente.get(endereco("configurar_criterio", estudo, variavel_id)).status_code == 403
    assert cliente.post(endereco("previa_criterio", estudo, variavel_id), {}).status_code == 403


def test_RN20_tela_abre_para_consulta_sem_botoes_de_alteracao(cliente, encerrado):
    estudo, criterio = encerrado
    pagina = cliente.get(endereco("criterios", estudo)).content.decode()
    assert "Estudo encerrado" in pagina
    assert criterio.descricao in pagina
    assert "regra-editar" not in pagina and "regra-remover" not in pagina
    assert pagina.count("disabled") >= 1


@pytest.mark.parametrize("situacao", [Estudo.Situacao.RASCUNHO, Estudo.Situacao.ATIVO])
def test_RN20_rascunho_e_ativo_continuam_aceitando_alteracao(cliente, estudo, situacao):
    estudo.situacao = situacao
    estudo.save()
    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, variavel("numero_filhos").id),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "1"},
    )
    assert resposta.status_code == 200
    assert Criterio.objects.count() == 1
