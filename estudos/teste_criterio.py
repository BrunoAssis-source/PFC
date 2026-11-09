from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from catalogo.models import OpcaoDominio, Variavel
from estudos.conftest import gravar, opcoes, variavel
from estudos.forms import CriterioForm
from estudos.models import Criterio

pytestmark = pytest.mark.django_db

EXCLUSAO = Criterio.TipoRegra.EXCLUSAO


@pytest.mark.parametrize(
    "operador, valor, ate, esperado",
    [
        ("entre", 18, 65, "Incluir participantes com idade entre 18 e 65 anos"),
        ("maior_igual", 18, None, "Incluir participantes com idade de pelo menos 18 anos"),
        ("menor_igual", 65, None, "Incluir participantes com idade de no máximo 65 anos"),
        ("igual", 30, None, "Incluir participantes com idade igual a 30 anos"),
        ("maior", 60, None, "Incluir participantes com idade acima de 60 anos"),
        ("menor", 18, None, "Incluir participantes com idade abaixo de 18 anos"),
        ("diferente", 40, None, "Incluir participantes com idade diferente de 40 anos"),
    ],
)
def test_frase_de_variavel_numerica(estudo, operador, valor, ate, esperado):
    criterio = gravar(estudo, "idade_anos", operador, valor_numero=valor, valor_numero_ate=ate)

    assert criterio.frase == esperado


@pytest.mark.parametrize(
    "operador, valor, ate, esperado",
    [
        ("maior_igual", "3000", None, "de pelo menos R$ 3.000"),
        ("menor_igual", "2500.50", None, "de no máximo R$ 2.500,50"),
        ("igual", "0", None, "igual a R$ 0"),
        ("entre", "1000", "1500000", "entre R$ 1.000 e R$ 1.500.000"),
    ],
)
def test_renda_aparece_no_padrao_brasileiro(estudo, operador, valor, ate, esperado):
    criterio = gravar(
        estudo, "renda_familiar_mensal", operador,
        valor_numero=Decimal(valor), valor_numero_ate=Decimal(ate) if ate else None,
    )

    assert criterio.frase == f"Incluir participantes com renda familiar {esperado}"


def test_numero_que_nao_e_dinheiro_leva_a_unidade_so_no_fim(estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    assert criterio.condicao == "entre 18 e 65 anos"


def test_resumo_do_estudo_formata_a_renda(estudo):
    gravar(estudo, "renda_familiar_mensal", "entre", valor_numero=1000, valor_numero_ate=100000)

    assert estudo.resumo_texto == "Serão incluídos participantes com renda familiar entre R$ 1.000 e R$ 100.000."


def test_faixa_da_variavel_em_reais_leva_o_simbolo_nas_duas_pontas():
    assert variavel("renda_familiar_mensal").faixa == "de R$ 0 a R$ 100.000"


def test_faixa_da_variavel_que_nao_e_dinheiro_leva_a_unidade(estudo):
    assert variavel("idade_anos").faixa == "de 0 a 120 anos"


def test_nome_do_criterio_no_admin_usa_a_descricao(estudo):
    criterio = gravar(estudo, "renda_familiar_mensal", "maior_igual", valor_numero=3000)

    assert str(criterio) == "renda familiar de pelo menos R$ 3.000"


def test_frase_de_exclusao_troca_o_verbo(estudo):
    criterio = gravar(estudo, "idade_anos", "menor", tipo_regra=EXCLUSAO, valor_numero=18)

    assert criterio.frase == "Excluir participantes com idade abaixo de 18 anos"


def test_criterio_nasce_como_inclusao(estudo):
    assert gravar(estudo, "idade_anos", "maior_igual", valor_numero=18).tipo_regra == "inclusao"


@pytest.mark.parametrize(
    "valores, esperado",
    [
        (["bissexual"], "orientação sexual: bissexual"),
        (["bissexual", "pansexual"], "orientação sexual: bissexual ou pansexual"),
        (["heterossexual", "bissexual", "outra"], "orientação sexual: heterossexual, bissexual ou outra"),
    ],
)
def test_frase_de_lista_com_uma_duas_e_tres_opcoes(estudo, valores, esperado):
    criterio = gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", *valores))

    assert criterio.frase == f"Incluir participantes com {esperado}"


def test_frase_de_lista_com_negacao(estudo):
    escolhidas = opcoes("raca_cor", "branca", "preta", "parda")
    criterio = gravar(estudo, "raca_cor", "nao_esta_em", escolhidas, tipo_regra=EXCLUSAO)

    assert criterio.frase == "Excluir participantes com raça ou cor diferente de branca, preta e parda"


@pytest.mark.parametrize(
    "operador, valores, esperado",
    [
        ("maior_igual", ["medio_completo"], "a partir de médio completo"),
        ("menor_igual", ["fundamental_completo"], "até fundamental completo"),
        ("e", ["superior_completo"], "igual a superior completo"),
        ("entre", ["medio_completo", "superior_completo"], "entre médio completo e superior completo"),
    ],
)
def test_frase_de_variavel_ordinal(estudo, operador, valores, esperado):
    criterio = gravar(estudo, "escolaridade", operador, opcoes("escolaridade", *valores))

    assert criterio.frase == f"Incluir participantes com escolaridade {esperado}"


@pytest.mark.parametrize("operador, resposta", [("verdadeiro", "sim"), ("falso", "não")])
def test_frase_de_variavel_booleana(estudo, operador, resposta):
    criterio = gravar(estudo, "cuidador_de_dependente", operador)

    assert criterio.frase == f"Incluir participantes com cuidador de dependente: {resposta}"


def test_frase_usa_o_nome_curto_da_variavel(estudo):
    criterio = gravar(estudo, "pessoas_no_domicilio", "maior_igual", valor_numero=3)

    assert criterio.frase.startswith("Incluir participantes com moradores do domicílio")


def test_frase_usa_o_nome_completo_quando_nao_ha_nome_curto(estudo):
    Variavel.objects.filter(codigo="idade_anos").update(nome_curto="")

    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    assert criterio.frase.startswith("Incluir participantes com idade em anos completos")


def test_resumo_do_estudo_sem_criterios(estudo):
    assert estudo.resumo_texto == ""
    assert estudo.resumo_criterios == "Nenhum critério definido"


def test_resumo_do_estudo_so_com_inclusao(estudo):
    gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    assert estudo.resumo_texto == "Serão incluídos participantes com idade entre 18 e 65 anos."
    assert estudo.resumo_criterios == "1 critério: 1 de inclusão"


def test_resumo_do_estudo_junta_inclusao_e_exclusao(estudo):
    gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", "bissexual", "pansexual"))
    gravar(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra=EXCLUSAO)

    assert estudo.resumo_texto == (
        "Serão incluídos participantes com idade entre 18 e 65 anos; "
        "orientação sexual: bissexual ou pansexual. "
        "Serão excluídos participantes com cuidador de dependente: sim."
    )
    assert estudo.resumo_criterios == "3 critérios: 2 de inclusão e 1 de exclusão"


def test_resumo_da_exclusao_nao_depende_de_haver_inclusao(estudo):
    gravar(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra=EXCLUSAO)

    assert estudo.resumo_texto == "Serão excluídos participantes com cuidador de dependente: sim."


def criterio_sem_gravar(codigo, operador, escolhidas=None, **campos):
    criterio = Criterio(variavel=variavel(codigo), operador=operador, **campos)
    criterio.opcoes_em_memoria = escolhidas
    return criterio


def test_criterio_numerico_completo_nao_tem_pendencia():
    assert criterio_sem_gravar("idade_anos", "maior_igual", valor_numero=18).pendencia() is None


@pytest.mark.parametrize("operador", ["maior_igual", "menor_igual", "igual"])
def test_condicao_de_um_valor_sem_valor_pede_o_valor(operador):
    criterio = criterio_sem_gravar("idade_anos", operador)

    assert criterio.pendencia() == "Informe o valor."


@pytest.mark.parametrize("campos", [{}, {"valor_numero": 18}, {"valor_numero_ate": 65}])
def test_entre_com_menos_de_dois_valores_pede_os_dois(campos):
    criterio = criterio_sem_gravar("idade_anos", "entre", **campos)

    assert criterio.pendencia() == "Informe os dois valores."


def test_entre_com_valores_fora_de_ordem_e_recusado():
    criterio = criterio_sem_gravar("idade_anos", "entre", valor_numero=65, valor_numero_ate=18)

    assert criterio.pendencia() == "O segundo valor precisa ser maior que o primeiro."


def test_valor_acima_do_maximo_plausivel_e_recusado():
    criterio = criterio_sem_gravar("idade_anos", "maior_igual", valor_numero=500)

    assert "máximo plausível" in criterio.pendencia()


def test_valor_abaixo_do_minimo_plausivel_e_recusado():
    criterio = criterio_sem_gravar("idade_anos", "maior_igual", valor_numero=-1)

    assert "mínimo plausível" in criterio.pendencia()


def test_lista_sem_opcao_pede_ao_menos_uma():
    criterio = criterio_sem_gravar("orientacao_sexual", "esta_em", [])

    assert criterio.pendencia() == "Escolha ao menos um valor."


def test_ordinal_aceita_um_nivel_so():
    dois_niveis = opcoes("escolaridade", "medio_completo", "pos_graduacao")

    criterio = criterio_sem_gravar("escolaridade", "maior_igual", dois_niveis)

    assert criterio.pendencia() == "Este operador aceita um valor só."


def test_ordinal_entre_pede_dois_niveis():
    criterio = criterio_sem_gravar("escolaridade", "entre", opcoes("escolaridade", "medio_completo"))

    assert criterio.pendencia() == "O operador entre exige dois valores."


def test_operador_que_nao_vale_para_o_tipo_e_recusado():
    criterio = criterio_sem_gravar("idade_anos", "esta_em")

    assert criterio.pendencia() == "Este operador não vale para o tipo da variável."


def test_booleana_nao_tem_pendencia_com_operador_valido():
    assert criterio_sem_gravar("cuidador_de_dependente", "falso").pendencia() is None


def formulario(codigo, dados):
    return CriterioForm(dados, variavel=variavel(codigo))


def test_formulario_numerico_valido_preenche_a_instancia():
    form = formulario("idade_anos", {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "65"})

    assert form.is_valid()
    assert form.instance.valor_numero == 18 and form.instance.valor_numero_ate == 65
    assert form.pendencia() is None


def test_formulario_sem_operador_pede_como_comparar():
    form = formulario("idade_anos", {"tipo_regra": "inclusao", "valor_numero": "18"})

    assert not form.is_valid()
    assert form.pendencia() == "Escolha como comparar."


def test_formulario_booleano_sem_resposta_pede_sim_ou_nao():
    form = formulario("cuidador_de_dependente", {"tipo_regra": "inclusao"})

    assert not form.is_valid()
    assert form.pendencia() == "Escolha sim ou não."


def test_formulario_nao_oferece_operador_fora_da_tela():
    form = formulario("idade_anos", {"tipo_regra": "inclusao", "operador": "diferente", "valor_numero": "18"})

    assert not form.is_valid()
    assert "operador" in form.errors


def test_formulario_de_lista_valida_as_opcoes_sem_gravar():
    form = formulario("orientacao_sexual", {"tipo_regra": "inclusao", "operador": "esta_em"})

    assert not form.is_valid()
    assert form.pendencia() == "Escolha ao menos um valor."


def test_validar_opcoes_levanta_a_mensagem_no_campo_certo():
    criterio = criterio_sem_gravar("orientacao_sexual", "esta_em", [])

    with pytest.raises(ValidationError) as erro:
        criterio.validar_opcoes()

    assert "opcoes" in erro.value.message_dict


def todas(codigo_do_dominio):
    return [opcao.id for opcao in OpcaoDominio.objects.filter(dominio__codigo=codigo_do_dominio)]


@pytest.mark.parametrize(
    "tipo_regra, aviso",
    [
        ("inclusao", "Esse critério inclui todos os participantes."),
        ("exclusao", "Esse critério exclui todos os participantes."),
    ],
)
def test_lista_com_todas_as_opcoes_marcadas_e_recusada(tipo_regra, aviso):
    form = formulario(
        "orientacao_sexual",
        {"tipo_regra": tipo_regra, "operador": "esta_em", "opcoes": todas("orientacao_sexual")},
    )

    assert not form.is_valid()
    assert form.pendencia() == aviso


def test_lista_com_todas_menos_uma_e_aceita():
    marcadas = todas("orientacao_sexual")[:-1]

    form = formulario("orientacao_sexual", {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": marcadas})

    assert form.is_valid()


def test_lista_de_duas_opcoes_recusa_marcar_as_duas_e_aceita_uma():
    ambas = todas("zona_residencia")

    assert not formulario("zona_residencia", {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": ambas}).is_valid()
    assert formulario("zona_residencia", {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": ambas[:1]}).is_valid()


def test_ordinal_com_nivel_intermediario_e_aceito():
    escolhida = [opcao.id for opcao in opcoes("escolaridade", "medio_completo")]

    form = formulario("escolaridade", {"tipo_regra": "inclusao", "operador": "maior_igual", "opcoes": escolhida})

    assert form.is_valid()
