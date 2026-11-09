from datetime import timedelta

import pytest
from django.utils import timezone

from estudos.models import Estudo
from voluntarios import cpf
from voluntarios.models import Participacao, ValorColetado, ValorSensivel, Voluntario
from voluntarios.pendencias import classificacao, pendentes, variaveis_faltantes

from .conftest import criterio, novo_estudo, opcoes, variavel
from .teste_verificacao import nascido_ha, valor


@pytest.fixture
def estudo(pesquisadora):
    return novo_estudo(pesquisadora)


@pytest.fixture
def voluntario(profissional):
    return Voluntario.objects.create(
        codigo_hmac=cpf.codigo("52998224725"), cpf_cifrado=cpf.cifrar("52998224725"), criado_por=profissional
    )


@pytest.fixture
def participacao(voluntario, estudo, profissional):
    # Os valores precisam de uma participação de origem. Ela fica em coleta, que a classificação ignora.
    outro = novo_estudo(estudo.pesquisador, "Estudo de origem")
    return Participacao.objects.create(
        voluntario=voluntario, estudo=outro, tcle_versao="1", registrado_por=profissional
    )


def classe(voluntario, estudo):
    return classificacao(voluntario.id, estudo.id)[(voluntario.id, estudo.id)]


def dar(participacao, profissional, codigo, **campos):
    return valor(participacao, codigo, profissional, **campos)


@pytest.fixture
def tres_criterios(estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "cuidador_de_dependente", "verdadeiro")
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    return estudo


def test_RN26_elegivel_atende_a_todos_os_criterios(voluntario, participacao, profissional, tres_criterios):
    dar(participacao, profissional, "numero_filhos", valor_numero=2)
    dar(participacao, profissional, "cuidador_de_dependente", valor_booleano=True)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])

    assert classe(voluntario, tres_criterios) == "elegivel"
    assert pendentes() == []


def test_RN26_inelegivel_deixa_de_atender_a_um_criterio(voluntario, participacao, profissional, tres_criterios):
    dar(participacao, profissional, "numero_filhos", valor_numero=0)
    dar(participacao, profissional, "cuidador_de_dependente", valor_booleano=True)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])

    assert classe(voluntario, tres_criterios) == "inelegivel"


def test_RN26_inelegivel_mesmo_faltando_outros_valores(voluntario, participacao, profissional, tres_criterios):
    dar(participacao, profissional, "numero_filhos", valor_numero=0)

    assert classe(voluntario, tres_criterios) == "inelegivel"
    assert pendentes() == []


def test_RN26_pendente_atende_aos_que_tem_e_falta_valor_para_um(voluntario, participacao, profissional, tres_criterios):
    dar(participacao, profissional, "numero_filhos", valor_numero=2)
    dar(participacao, profissional, "cuidador_de_dependente", valor_booleano=True)

    assert classe(voluntario, tres_criterios) == "pendente"
    [linha] = pendentes()
    assert [v.codigo for v in linha["variaveis"]] == ["sexo_ao_nascer"]
    assert linha["codigo"] == voluntario.codigo_hmac[:8]


def test_RN26_exclusao_atendida_deixa_inelegivel(voluntario, participacao, profissional, estudo):
    criterio(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra="exclusao")
    dar(participacao, profissional, "cuidador_de_dependente", valor_booleano=True)

    assert classe(voluntario, estudo) == "inelegivel"


def test_estudo_sem_criterios_deixa_todo_voluntario_elegivel(voluntario, estudo):
    assert classe(voluntario, estudo) == "elegivel"


def test_idade_faltante_pede_a_data_de_nascimento(voluntario, participacao, profissional, estudo):
    criterio(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])

    assert classe(voluntario, estudo) == "pendente"
    assert [v.codigo for v in variaveis_faltantes(voluntario.id, estudo.id)] == ["data_nascimento"]

    dar(participacao, profissional, "data_nascimento", valor_data=nascido_ha(30))
    assert classe(voluntario, estudo) == "elegivel"
    assert variaveis_faltantes(voluntario.id, estudo.id) == []


def test_faixa_etaria_faltante_tambem_pede_so_a_data_de_nascimento(voluntario, participacao, profissional, estudo):
    criterio(estudo, "faixa_etaria", "e", opcoes("faixa_etaria", "30_39"))
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])

    assert [v.codigo for v in variaveis_faltantes(voluntario.id, estudo.id)] == ["data_nascimento"]


def test_renda_per_capita_faltante_pede_so_a_origem_que_falta(voluntario, participacao, profissional, estudo):
    criterio(estudo, "renda_per_capita", "menor_igual", valor_numero=1000)
    dar(participacao, profissional, "renda_familiar_mensal", valor_numero=3000)

    assert classe(voluntario, estudo) == "pendente"
    assert [v.codigo for v in variaveis_faltantes(voluntario.id, estudo.id)] == ["pessoas_no_domicilio"]


def test_valor_vencido_deixa_de_valer_e_volta_a_ser_faltante(voluntario, participacao, profissional, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    dado = dar(participacao, profissional, "numero_filhos", valor_numero=2)
    assert variavel("numero_filhos").vida_util_dias == 365
    assert classe(voluntario, estudo) == "elegivel"

    ValorColetado.objects.filter(pk=dado.pk).update(coletado_em=timezone.now() - timedelta(days=400))

    assert classe(voluntario, estudo) == "pendente"
    assert [v.codigo for v in variaveis_faltantes(voluntario.id, estudo.id)] == ["numero_filhos"]


def test_variavel_permanente_nao_vence(voluntario, participacao, profissional, estudo):
    criterio(estudo, "idade_anos", "maior_igual", valor_numero=18)
    dado = dar(participacao, profissional, "data_nascimento", valor_data=nascido_ha(30))
    ValorColetado.objects.filter(pk=dado.pk).update(coletado_em=timezone.now() - timedelta(days=5000))

    assert classe(voluntario, estudo) == "elegivel"


def test_derivada_some_quando_a_origem_vence(voluntario, participacao, profissional, estudo):
    criterio(estudo, "renda_per_capita", "menor_igual", valor_numero=1000)
    renda = dar(participacao, profissional, "renda_familiar_mensal", valor_numero=3000)
    dar(participacao, profissional, "pessoas_no_domicilio", valor_numero=3)
    assert classe(voluntario, estudo) == "elegivel"

    ValorColetado.objects.filter(pk=renda.pk).update(coletado_em=timezone.now() - timedelta(days=400))

    assert classe(voluntario, estudo) == "pendente"
    assert [v.codigo for v in variaveis_faltantes(voluntario.id, estudo.id)] == ["renda_familiar_mensal"]


def test_valor_sensivel_entra_na_classificacao_e_a_faltante_sensivel_vem_por_ultimo(
    voluntario, participacao, profissional, estudo
):
    criterio(estudo, "pessoa_com_deficiencia", "falso")
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])

    assert [v.codigo for v in variaveis_faltantes(voluntario.id, estudo.id)] == ["numero_filhos", "pessoa_com_deficiencia"]

    dar(participacao, profissional, "numero_filhos", valor_numero=2)
    dar(participacao, profissional, "pessoa_com_deficiencia", modelo=ValorSensivel, valor_booleano=False)
    assert classe(voluntario, estudo) == "elegivel"


def test_coleta_encerrada_por_criterio_deixa_inelegivel(voluntario, participacao, profissional, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    eliminada = Participacao.objects.create(
        voluntario=voluntario, estudo=estudo, tcle_versao="1", registrado_por=profissional,
        situacao=Participacao.Situacao.ELIMINADA,
    )

    assert classe(voluntario, estudo) == "inelegivel"
    assert pendentes() == []
    assert eliminada.situacao == "eliminada"


def test_participacao_em_coleta_nao_muda_a_classificacao(voluntario, participacao, profissional, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    Participacao.objects.create(voluntario=voluntario, estudo=estudo, tcle_versao="1", registrado_por=profissional)

    assert classe(voluntario, estudo) == "pendente"
    assert len(pendentes()) == 1


def test_so_estudos_ativos_entram(voluntario, participacao, profissional, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    for situacao in (Estudo.Situacao.RASCUNHO, Estudo.Situacao.ENCERRADO):
        estudo.situacao = situacao
        estudo.save()
        assert (voluntario.id, estudo.id) not in classificacao()
        assert pendentes() == []


def test_voluntario_sem_nenhum_valor_nao_e_listado_como_pendente(voluntario, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)

    assert classe(voluntario, estudo) == "pendente"
    assert pendentes() == []


def test_pendente_so_aparece_nos_estudos_em_que_falta_valor(voluntario, participacao, profissional, estudo, pesquisadora):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    outro = novo_estudo(pesquisadora, "Já atendido")
    criterio(outro, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    dar(participacao, profissional, "sexo_ao_nascer", opcao=opcoes("sexo_ao_nascer", "feminino")[0])

    assert [linha["estudo"] for linha in pendentes()] == [estudo]
    assert classe(voluntario, outro) == "elegivel"
