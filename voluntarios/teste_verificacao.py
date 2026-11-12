from datetime import date
from decimal import Decimal

import pytest
from django.db import connection

from estudos.models import Criterio
from voluntarios.models import ValorColetado, ValorSensivel

from .conftest import criterio, nova_participacao, novo_estudo, opcoes, variavel

EXCLUSAO = Criterio.TipoRegra.EXCLUSAO


def valor(participacao, codigo, usuario, modelo=ValorColetado, **campos):
    return modelo.objects.create(
        codigo_voluntario=participacao.voluntario.codigo_hmac,
        variavel=variavel(codigo),
        participacao=participacao,
        coletado_por=usuario,
        fonte="voluntario",
        **campos,
    )


def cumpre(participacao):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT criterio_id, cumpre FROM voluntarios_avaliacao_criterio WHERE participacao_id = %s",
            [participacao.id],
        )
        return dict(cursor.fetchall())


@pytest.fixture
def base(profissional, pesquisadora):
    estudo = novo_estudo(pesquisadora)
    return estudo, nova_participacao(profissional, estudo)


@pytest.mark.parametrize(
    "operador, valor_criterio, ate, resposta, atende",
    [
        ("igual", 2, None, 2, True),
        ("igual", 2, None, 3, False),
        ("diferente", 2, None, 3, True),
        ("diferente", 2, None, 2, False),
        ("menor", 2, None, 1, True),
        ("menor", 2, None, 2, False),
        ("menor_igual", 2, None, 2, True),
        ("menor_igual", 2, None, 3, False),
        ("maior", 2, None, 3, True),
        ("maior", 2, None, 2, False),
        ("maior_igual", 2, None, 2, True),
        ("maior_igual", 2, None, 1, False),
        ("entre", 2, 4, 2, True),
        ("entre", 2, 4, 4, True),
        ("entre", 2, 4, 5, False),
        ("entre", 2, 4, 1, False),
    ],
)
def test_operadores_numericos(base, profissional, operador, valor_criterio, ate, resposta, atende):
    estudo, participacao = base
    inclusao = criterio(estudo, "numero_filhos", operador, valor_numero=valor_criterio, valor_numero_ate=ate)
    exclusao = criterio(
        estudo, "numero_filhos", operador, tipo_regra=EXCLUSAO, valor_numero=valor_criterio, valor_numero_ate=ate
    )
    valor(participacao, "numero_filhos", profissional, valor_numero=resposta)
    resultado = cumpre(participacao)
    assert resultado[inclusao.id] is atende
    assert resultado[exclusao.id] is (not atende)


@pytest.mark.parametrize(
    "operador, escolhidas, resposta, atende",
    [
        ("e", ["feminino"], "feminino", True),
        ("e", ["feminino"], "masculino", False),
        ("nao_e", ["feminino"], "masculino", True),
        ("nao_e", ["feminino"], "feminino", False),
        ("esta_em", ["feminino", "intersexo"], "intersexo", True),
        ("esta_em", ["feminino", "intersexo"], "masculino", False),
        ("nao_esta_em", ["feminino", "intersexo"], "masculino", True),
        ("nao_esta_em", ["feminino", "intersexo"], "feminino", False),
    ],
)
def test_operadores_nominais(base, profissional, operador, escolhidas, resposta, atende):
    estudo, participacao = base
    regra = criterio(estudo, "sexo_ao_nascer", operador, opcoes("sexo_ao_nascer", *escolhidas))
    valor(participacao, "sexo_ao_nascer", profissional, opcao=opcoes("sexo_ao_nascer", resposta)[0])
    assert cumpre(participacao)[regra.id] is atende


@pytest.mark.parametrize(
    "operador, escolhidas, resposta, atende",
    [
        ("e", ["medio_completo"], "medio_completo", True),
        ("e", ["medio_completo"], "superior_completo", False),
        ("nao_e", ["medio_completo"], "superior_completo", True),
        ("esta_em", ["medio_completo", "pos_graduacao"], "pos_graduacao", True),
        ("esta_em", ["medio_completo", "pos_graduacao"], "superior_completo", False),
        ("nao_esta_em", ["medio_completo", "pos_graduacao"], "superior_completo", True),
        ("maior_igual", ["medio_completo"], "medio_completo", True),
        ("maior_igual", ["medio_completo"], "superior_completo", True),
        ("maior_igual", ["medio_completo"], "medio_incompleto", False),
        ("menor_igual", ["medio_completo"], "medio_completo", True),
        ("menor_igual", ["medio_completo"], "fundamental_completo", True),
        ("menor_igual", ["medio_completo"], "superior_incompleto", False),
        ("entre", ["medio_incompleto", "superior_completo"], "medio_completo", True),
        ("entre", ["medio_incompleto", "superior_completo"], "superior_completo", True),
        ("entre", ["medio_incompleto", "superior_completo"], "pos_graduacao", False),
        ("entre", ["medio_incompleto", "superior_completo"], "fundamental_completo", False),
    ],
)
def test_operadores_ordinais_comparam_pela_ordem_dos_niveis(base, profissional, operador, escolhidas, resposta, atende):
    estudo, participacao = base
    regra = criterio(estudo, "escolaridade", operador, opcoes("escolaridade", *escolhidas))
    valor(participacao, "escolaridade", profissional, opcao=opcoes("escolaridade", resposta)[0])
    assert cumpre(participacao)[regra.id] is atende


@pytest.mark.parametrize(
    "operador, resposta, atende",
    [("verdadeiro", True, True), ("verdadeiro", False, False), ("falso", False, True), ("falso", True, False)],
)
def test_operadores_booleanos(base, profissional, operador, resposta, atende):
    estudo, participacao = base
    regra = criterio(estudo, "cuidador_de_dependente", operador)
    valor(participacao, "cuidador_de_dependente", profissional, valor_booleano=resposta)
    assert cumpre(participacao)[regra.id] is atende


@pytest.mark.parametrize(
    "operador, referencia, ate, resposta, atende",
    [
        ("antes", date(1995, 1, 1), None, date(1990, 1, 1), True),
        ("antes", date(1995, 1, 1), None, date(2000, 1, 1), False),
        ("depois", date(1995, 1, 1), None, date(2000, 1, 1), True),
        ("depois", date(1995, 1, 1), None, date(1990, 1, 1), False),
        ("entre", date(2000, 1, 1), date(2005, 1, 1), date(2002, 6, 1), True),
        ("entre", date(2000, 1, 1), date(2005, 1, 1), date(2010, 6, 1), False),
    ],
)
def test_operadores_de_data(base, profissional, operador, referencia, ate, resposta, atende):
    estudo, participacao = base
    regra = criterio(estudo, "data_nascimento", operador, valor_data=referencia, valor_data_ate=ate)
    valor(participacao, "data_nascimento", profissional, valor_data=resposta)
    assert cumpre(participacao)[regra.id] is atende


def test_criterio_sem_resposta_nao_aparece(base):
    estudo, participacao = base
    criterio(estudo, "numero_filhos", "igual", valor_numero=1)
    assert cumpre(participacao) == {}


def test_vale_o_valor_mais_recente(base, profissional):
    estudo, participacao = base
    regra = criterio(estudo, "numero_filhos", "igual", valor_numero=2)
    valor(participacao, "numero_filhos", profissional, valor_numero=1)
    valor(participacao, "numero_filhos", profissional, valor_numero=2)
    assert cumpre(participacao)[regra.id] is True


def test_valor_sensivel_entra_na_verificacao(base, profissional):
    estudo, participacao = base
    regra = criterio(estudo, "pessoa_com_deficiencia", "verdadeiro")
    valor(participacao, "pessoa_com_deficiencia", profissional, modelo=ValorSensivel, valor_booleano=True)
    assert cumpre(participacao)[regra.id] is True


def nascido_ha(anos):
    hoje = date.today()
    return date(hoje.year - anos, hoje.month, min(hoje.day, 28))


def test_idade_sai_da_data_de_nascimento_sem_ser_gravada(base, profissional):
    estudo, participacao = base
    regra = criterio(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    valor(participacao, "data_nascimento", profissional, valor_data=nascido_ha(30))
    assert cumpre(participacao)[regra.id] is True
    assert not ValorColetado.objects.filter(variavel=variavel("idade_anos")).exists()


def test_idade_fora_da_faixa_reprova(base, profissional):
    estudo, participacao = base
    regra = criterio(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    valor(participacao, "data_nascimento", profissional, valor_data=nascido_ha(70))
    assert cumpre(participacao)[regra.id] is False


@pytest.mark.parametrize(
    "anos, faixa",
    [(10, "ate_17"), (18, "18_29"), (35, "30_39"), (45, "40_49"), (59, "50_59"), (60, "60_69"), (85, "70_mais")],
)
def test_faixa_etaria_sai_da_idade(base, profissional, anos, faixa):
    estudo, participacao = base
    regra = criterio(estudo, "faixa_etaria", "e", opcoes("faixa_etaria", faixa))
    valor(participacao, "data_nascimento", profissional, valor_data=nascido_ha(anos))
    assert cumpre(participacao)[regra.id] is True


def test_renda_per_capita_divide_pelas_pessoas_do_domicilio(base, profissional):
    estudo, participacao = base
    regra = criterio(estudo, "renda_per_capita", "menor_igual", valor_numero=Decimal("1000"))
    valor(participacao, "renda_familiar_mensal", profissional, valor_numero=Decimal("3000"))
    assert cumpre(participacao) == {}
    valor(participacao, "pessoas_no_domicilio", profissional, valor_numero=Decimal("3"))
    assert cumpre(participacao)[regra.id] is True
    valor(participacao, "pessoas_no_domicilio", profissional, valor_numero=Decimal("2"))
    assert cumpre(participacao)[regra.id] is False


def test_pessoas_no_domicilio_tem_minimo_um(db):
    # O mínimo de 1 no catálogo é o que impede a divisão por zero da renda per capita.
    assert variavel("pessoas_no_domicilio").minimo == 1
