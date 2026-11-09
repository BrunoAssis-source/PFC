import pytest
from django.urls import reverse

from catalogo.models import Variavel
from estudos.conftest import gravar, variavel
from estudos.models import Criterio

pytestmark = pytest.mark.django_db

EXCLUSAO = Criterio.TipoRegra.EXCLUSAO


def test_variavel_traz_um_texto_para_cada_resposta():
    deficiencia = variavel("pessoa_com_deficiencia")

    assert (deficiencia.texto_sim, deficiencia.texto_nao) == ("com deficiência", "sem deficiência")


@pytest.mark.parametrize(
    "operador, regra, esperado",
    [
        ("verdadeiro", "inclusao", "Incluir participantes com deficiência"),
        ("falso", "inclusao", "Incluir participantes sem deficiência"),
        ("verdadeiro", "exclusao", "Excluir participantes com deficiência"),
        ("falso", "exclusao", "Excluir participantes sem deficiência"),
    ],
)
def test_frase_de_pessoa_com_deficiencia(estudo, operador, regra, esperado):
    criterio = gravar(estudo, "pessoa_com_deficiencia", operador, tipo_regra=regra)

    assert criterio.frase == esperado


def test_frase_nao_repete_o_nome_da_variavel(estudo):
    frase = gravar(estudo, "pessoa_com_deficiencia", "verdadeiro").frase

    assert "pessoa com deficiência" not in frase
    assert ": sim" not in frase


@pytest.mark.parametrize("operador, texto", [("verdadeiro", "com deficiência"), ("falso", "sem deficiência")])
def test_descricao_na_lista_de_regras_e_o_texto_da_resposta(estudo, operador, texto):
    assert gravar(estudo, "pessoa_com_deficiencia", operador).descricao == texto


def test_resumo_so_com_deficiencia_na_inclusao(estudo):
    gravar(estudo, "pessoa_com_deficiencia", "verdadeiro")

    assert estudo.resumo_texto == "Serão incluídos participantes com deficiência."


def test_resumo_sem_deficiencia_na_exclusao(estudo):
    gravar(estudo, "pessoa_com_deficiencia", "falso", tipo_regra=EXCLUSAO)

    assert estudo.resumo_texto == "Serão excluídos participantes sem deficiência."


def test_resumo_com_deficiencia_depois_de_outro_criterio_nao_repete_o_com(estudo):
    gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    gravar(estudo, "pessoa_com_deficiencia", "falso")

    assert estudo.resumo_texto == "Serão incluídos participantes com idade entre 18 e 65 anos; sem deficiência."


def test_resumo_com_deficiencia_antes_de_outro_criterio(estudo):
    # A lista sai ordenada pelo código da variável, e "pessoa_..." vem antes de "renda_...".
    gravar(estudo, "renda_familiar_mensal", "maior_igual", valor_numero=3000)
    gravar(estudo, "pessoa_com_deficiencia", "verdadeiro")

    assert estudo.resumo_texto == "Serão incluídos participantes com deficiência; renda familiar de pelo menos R$ 3.000."


def test_resumo_junta_inclusao_e_exclusao_com_a_deficiencia(estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    gravar(estudo, "pessoa_com_deficiencia", "verdadeiro", tipo_regra=EXCLUSAO)

    assert estudo.resumo_texto == (
        "Serão incluídos participantes com idade de pelo menos 18 anos. "
        "Serão excluídos participantes com deficiência."
    )


def test_outra_variavel_sim_ou_nao_continua_com_a_frase_padrao(estudo):
    criterio = gravar(estudo, "cuidador_de_dependente", "verdadeiro")

    assert criterio.frase == "Incluir participantes com cuidador de dependente: sim"
    assert estudo.resumo_texto == "Serão incluídos participantes com cuidador de dependente: sim."


def test_variavel_sem_texto_proprio_usa_o_padrao_mesmo_na_resposta_nao(estudo):
    assert variavel("cuidador_de_dependente").texto_nao == ""
    assert gravar(estudo, "cuidador_de_dependente", "falso").frase == "Incluir participantes com cuidador de dependente: não"


def test_texto_proprio_so_vale_para_sim_ou_nao():
    Variavel.objects.filter(codigo="idade_anos").update(texto_sim="nunca usado")
    criterio = Criterio(variavel=variavel("idade_anos"), operador="maior_igual", valor_numero=18)

    assert criterio.resposta_propria == ""
    assert criterio.frase == "Incluir participantes com idade de pelo menos 18 anos"


def test_previa_e_lista_da_tela_mostram_a_frase_corrigida(cliente, estudo):
    codigo = variavel("pessoa_com_deficiencia").id
    previa = cliente.get(
        reverse("estudos:previa_criterio", args=[estudo.id, codigo]), {"tipo_regra": "inclusao", "operador": "falso"}
    ).content.decode()
    adicionado = cliente.post(
        reverse("estudos:adicionar_criterio", args=[estudo.id, codigo]), {"tipo_regra": "inclusao", "operador": "falso"}
    ).content.decode()

    assert "Incluir participantes sem deficiência." in previa
    assert "Serão incluídos participantes sem deficiência." in adicionado
    assert "pessoa com deficiência" not in adicionado


def test_detalhe_do_estudo_mostra_o_resumo_corrigido(cliente, estudo):
    gravar(estudo, "pessoa_com_deficiencia", "verdadeiro")

    html = cliente.get(reverse("estudos:detalhe", args=[estudo.id])).content.decode()

    assert "Serão incluídos participantes com deficiência." in html
