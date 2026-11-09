import pytest
from django.urls import reverse

from estudos.conftest import gravar, opcoes, variavel
from estudos.models import Criterio

pytestmark = pytest.mark.django_db

AVISO = "Esta variável já é usada em um critério deste estudo."


def endereco(nome, estudo, *args):
    return reverse(f"estudos:{nome}", args=[estudo.id, *args])


def adicionar(cliente, estudo, codigo, dados):
    return cliente.post(endereco("adicionar_criterio", estudo, variavel(codigo).id), dados)


def previa(cliente, estudo, codigo, dados):
    return cliente.post(endereco("previa_criterio", estudo, variavel(codigo).id), dados).content.decode()


IDADE = {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "18"}


def test_RF06_CA03_servidor_recusa_variavel_ja_usada_no_estudo(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = adicionar(cliente, estudo, "idade_anos", IDADE)

    assert resposta.status_code == 422
    assert AVISO in resposta.content.decode()
    assert Criterio.objects.count() == 1


def test_RN19_recusa_mesmo_com_outra_regra_ou_outro_valor(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    exclusao = adicionar(
        cliente, estudo, "idade_anos", {"tipo_regra": "exclusao", "operador": "maior_igual", "valor_numero": "65"}
    )

    assert exclusao.status_code == 422
    assert Criterio.objects.count() == 1


def test_RN19_variavel_booleana_e_de_lista_tambem_nao_se_repetem(cliente, estudo):
    gravar(estudo, "cuidador_de_dependente", "verdadeiro")
    gravar(estudo, "sexo_ao_nascer", "esta_em", opcoes("sexo_ao_nascer", "feminino"))

    sim = adicionar(cliente, estudo, "cuidador_de_dependente", {"tipo_regra": "inclusao", "operador": "falso"})
    lista = adicionar(
        cliente,
        estudo,
        "sexo_ao_nascer",
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [opcoes("sexo_ao_nascer", "masculino")[0].id]},
    )

    assert sim.status_code == 422 and lista.status_code == 422
    assert Criterio.objects.count() == 2


def test_RN19_previa_avisa_e_nao_libera_o_botao(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    html = previa(cliente, estudo, "idade_anos", IDADE)

    assert 'data-completo="0"' in html
    assert AVISO in html


def test_RN19_outra_variavel_continua_permitida(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = adicionar(
        cliente, estudo, "numero_filhos", {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "1"}
    )

    assert resposta.status_code == 200
    assert Criterio.objects.count() == 2


def test_RN19_mesma_variavel_em_outro_estudo_e_permitida(cliente, estudo, pesquisadora):
    from estudos.models import Estudo

    outro = Estudo.objects.create(nome="Outro", condicao="Outra", pesquisador=pesquisadora)
    gravar(outro, "idade_anos", "maior_igual", valor_numero=18)

    assert adicionar(cliente, estudo, "idade_anos", IDADE).status_code == 200


def test_RN19_editar_o_proprio_criterio_nao_conta_como_repeticao(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = cliente.post(
        endereco("editar_criterio", estudo, criterio.id),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "21"},
    )

    assert resposta.status_code == 200
    criterio.refresh_from_db()
    assert criterio.valor_numero == 21


def test_RN13_variavel_em_uso_aparece_indisponivel_na_arvore_e_na_busca(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    uso = variavel("idade_anos")
    livre = variavel("numero_filhos")

    tela = cliente.get(endereco("criterios", estudo)).content.decode()
    busca = cliente.get(endereco("buscar_variaveis", estudo), {"q": "idade"}).content.decode()

    for pagina in (tela, busca):
        assert f'data-variavel="{uso.id}"' in pagina
        trecho = pagina.split(f'data-variavel="{uso.id}"')[1].split("</button>")[0]
        assert "disabled" in trecho and "em uso" in trecho
    trecho_livre = tela.split(f'data-variavel="{livre.id}"')[1].split("</button>")[0]
    assert "disabled" not in trecho_livre
