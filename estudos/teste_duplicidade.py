import pytest
from django.urls import reverse

from catalogo.models import OpcaoDominio
from estudos.conftest import gravar, opcoes, variavel
from estudos.forms import CriterioForm
from estudos.models import Criterio, Estudo

pytestmark = pytest.mark.django_db

AVISO = "Este critério já existe neste estudo."


def endereco(nome, estudo, *args):
    return reverse(f"estudos:{nome}", args=[estudo.id, *args])


def adicionar(cliente, estudo, codigo, dados):
    return cliente.post(endereco("adicionar_criterio", estudo, variavel(codigo).id), dados)


def previa(cliente, estudo, codigo, dados):
    return cliente.post(endereco("previa_criterio", estudo, variavel(codigo).id), dados).content.decode()


def ids(codigo_do_dominio, *valores):
    return [o.id for o in opcoes(codigo_do_dominio, *valores)]


IDADE = {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "18"}


def test_servidor_recusa_o_mesmo_criterio_numerico_duas_vezes(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = adicionar(cliente, estudo, "idade_anos", IDADE)

    assert resposta.status_code == 422
    assert AVISO in resposta.content.decode()
    assert Criterio.objects.count() == 1


def test_valor_igual_escrito_de_outro_jeito_tambem_e_duplicado(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = adicionar(cliente, estudo, "idade_anos", {**IDADE, "valor_numero": "18.00"})

    assert resposta.status_code == 422
    assert Criterio.objects.count() == 1


def test_previa_avisa_do_duplicado_e_nao_libera_o_botao(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    html = previa(cliente, estudo, "idade_anos", IDADE)

    assert 'data-completo="0"' in html
    assert AVISO in html


@pytest.mark.parametrize(
    "dados",
    [
        {**IDADE, "valor_numero": "21"},
        {**IDADE, "operador": "menor_igual"},
        {**IDADE, "tipo_regra": "exclusao"},
    ],
)
def test_condicao_diferente_nao_e_duplicada(cliente, estudo, dados):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    assert adicionar(cliente, estudo, "idade_anos", dados).status_code == 200
    assert Criterio.objects.count() == 2


def test_entre_com_outro_segundo_valor_nao_e_duplicado(cliente, estudo):
    gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    dados = {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "70"}

    assert adicionar(cliente, estudo, "idade_anos", dados).status_code == 200


def test_entre_igual_e_duplicado(cliente, estudo):
    gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    dados = {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "65"}

    assert adicionar(cliente, estudo, "idade_anos", dados).status_code == 422


def test_lista_com_as_mesmas_opcoes_em_outra_ordem_e_duplicada(cliente, estudo):
    gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", "bissexual", "pansexual"))
    marcadas = ids("orientacao_sexual", "pansexual", "bissexual")

    resposta = adicionar(cliente, estudo, "orientacao_sexual", {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": marcadas})

    assert resposta.status_code == 422
    assert AVISO in resposta.content.decode()


def test_lista_com_uma_opcao_a_mais_nao_e_duplicada(cliente, estudo):
    gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", "bissexual"))
    marcadas = ids("orientacao_sexual", "bissexual", "pansexual")

    resposta = adicionar(cliente, estudo, "orientacao_sexual", {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": marcadas})

    assert resposta.status_code == 200


def test_ordinal_igual_e_duplicado(cliente, estudo):
    gravar(estudo, "escolaridade", "maior_igual", opcoes("escolaridade", "medio_completo"))
    dados = {"tipo_regra": "inclusao", "operador": "maior_igual", "opcoes": ids("escolaridade", "medio_completo")}

    assert adicionar(cliente, estudo, "escolaridade", dados).status_code == 422


def test_sim_ou_nao_repetido_e_duplicado(cliente, estudo):
    gravar(estudo, "cuidador_de_dependente", "verdadeiro")

    repetido = adicionar(cliente, estudo, "cuidador_de_dependente", {"tipo_regra": "inclusao", "operador": "verdadeiro"})
    oposto = adicionar(cliente, estudo, "cuidador_de_dependente", {"tipo_regra": "inclusao", "operador": "falso"})

    assert repetido.status_code == 422
    assert oposto.status_code == 200


def test_municipios_iguais_sao_duplicados(cliente, estudo):
    mogi = OpcaoDominio.objects.get(valor="3530607")
    gravar(estudo, "municipio_residencia", "esta_em", [mogi])

    resposta = adicionar(cliente, estudo, "municipio_residencia", {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [mogi.id]})

    assert resposta.status_code == 422


def test_mesmo_criterio_em_outro_estudo_e_permitido(cliente, pesquisadora, estudo):
    outro = Estudo.objects.create(nome="Outro estudo", condicao="c", pesquisador=pesquisadora)
    gravar(outro, "idade_anos", "maior_igual", valor_numero=18)

    assert adicionar(cliente, estudo, "idade_anos", IDADE).status_code == 200


def test_salvar_a_edicao_sem_mudar_nao_conta_como_duplicado_de_si_mesmo(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = cliente.post(endereco("editar_criterio", estudo, criterio.id), IDADE)

    assert resposta.status_code == 200


def test_editar_para_ficar_igual_a_outro_criterio_e_recusado(cliente, estudo):
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    outro = gravar(estudo, "idade_anos", "maior_igual", valor_numero=30)

    resposta = cliente.post(endereco("editar_criterio", estudo, outro.id), IDADE)

    assert resposta.status_code == 422
    assert AVISO in resposta.content.decode()
    outro.refresh_from_db()
    assert outro.valor_numero == 30


def test_formulario_sem_estudo_nao_checa_duplicidade():
    form = CriterioForm(IDADE, variavel=variavel("idade_anos"))

    assert form.is_valid()


def test_segundo_valor_residual_fora_do_entre_nao_esconde_o_duplicado(cliente, estudo):
    # Dado antigo pode ter sobra no segundo valor de uma condição que não é "entre".
    gravar(estudo, "idade_anos", "maior_igual", valor_numero=18, valor_numero_ate=65)

    assert adicionar(cliente, estudo, "idade_anos", IDADE).status_code == 422
