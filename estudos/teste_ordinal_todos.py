import pytest
from django.urls import reverse

from estudos.conftest import opcoes, variavel
from estudos.forms import CriterioForm
from estudos.models import Criterio

pytestmark = pytest.mark.django_db

# Escolaridade vai de "sem instrução" (mais baixo) a "pós-graduação" (mais alto).
MAIS_BAIXO = "sem_instrucao"
MAIS_ALTO = "pos_graduacao"


def ids(*valores):
    return [o.id for o in opcoes("escolaridade", *valores)]


def adicionar(cliente, estudo, dados):
    return cliente.post(reverse("estudos:adicionar_criterio", args=[estudo.id, variavel("escolaridade").id]), dados)


@pytest.mark.parametrize(
    "operador, niveis",
    [
        ("maior_igual", [MAIS_BAIXO]),
        ("menor_igual", [MAIS_ALTO]),
    ],
)
def test_condicao_que_cobre_a_escala_inteira_e_recusada(cliente, estudo, operador, niveis):
    resposta = adicionar(cliente, estudo, {"tipo_regra": "inclusao", "operador": operador, "opcoes": ids(*niveis)})

    assert resposta.status_code == 422
    assert "Esse critério inclui todos os participantes." in resposta.content.decode()
    assert Criterio.objects.count() == 0


def test_exclusao_que_cobre_a_escala_inteira_diz_que_exclui_todos(cliente, estudo):
    resposta = adicionar(cliente, estudo, {"tipo_regra": "exclusao", "operador": "maior_igual", "opcoes": ids(MAIS_BAIXO)})

    assert resposta.status_code == 422
    assert "Esse critério exclui todos os participantes." in resposta.content.decode()


@pytest.mark.parametrize(
    "operador, niveis",
    [
        ("maior_igual", ["fundamental_incompleto"]),
        ("maior_igual", [MAIS_ALTO]),
        ("menor_igual", ["superior_completo"]),
        ("menor_igual", [MAIS_BAIXO]),
        ("e", [MAIS_BAIXO]),
        ("e", [MAIS_ALTO]),
    ],
)
def test_condicao_que_restringe_e_aceita(cliente, estudo, operador, niveis):
    resposta = adicionar(cliente, estudo, {"tipo_regra": "inclusao", "operador": operador, "opcoes": ids(*niveis)})

    assert resposta.status_code == 200
    assert Criterio.objects.count() == 1


def test_previa_avisa_e_nao_libera_o_botao(cliente, estudo):
    resposta = cliente.post(
        reverse("estudos:previa_criterio", args=[estudo.id, variavel("escolaridade").id]),
        {"tipo_regra": "inclusao", "operador": "menor_igual", "opcoes": ids(MAIS_ALTO)},
    ).content.decode()

    assert 'data-completo="0"' in resposta
    assert "Esse critério inclui todos os participantes." in resposta


def test_formulario_decide_pela_ordem_da_escala_e_nao_pelo_nome_do_nivel():
    form = CriterioForm(
        {"tipo_regra": "inclusao", "operador": "maior_igual", "opcoes": ids("fundamental_incompleto")},
        variavel=variavel("escolaridade"),
    )

    assert form.is_valid()
    assert form.cobre_todas_as_opcoes("maior_igual", opcoes("escolaridade", MAIS_BAIXO))
    assert not form.cobre_todas_as_opcoes("maior_igual", opcoes("escolaridade", "fundamental_incompleto"))


def test_lista_comum_continua_exigindo_marcar_todas_as_opcoes():
    form = CriterioForm(
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [o.id for o in opcoes("orientacao_sexual", "bissexual")]},
        variavel=variavel("orientacao_sexual"),
    )

    assert form.is_valid()


def test_editar_para_cobrir_a_escala_inteira_e_recusado(cliente, estudo):
    from estudos.conftest import gravar

    criterio = gravar(estudo, "escolaridade", "maior_igual", opcoes("escolaridade", "medio_completo"))

    resposta = cliente.post(
        reverse("estudos:editar_criterio", args=[estudo.id, criterio.id]),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "opcoes": ids(MAIS_BAIXO)},
    )

    assert resposta.status_code == 422
    assert list(criterio.opcoes.all()) == opcoes("escolaridade", "medio_completo")
