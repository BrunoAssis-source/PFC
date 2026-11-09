import pytest
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from estudos.models import Criterio
from voluntarios.coleta import proxima_variavel, variaveis_da_coleta
from voluntarios.models import Participacao, ValorColetado, ValorSensivel

from .conftest import criterio, nova_participacao, novo_estudo, opcoes

EXCLUSAO = Criterio.TipoRegra.EXCLUSAO


def url(participacao):
    return reverse("voluntarios:coleta", args=[participacao.voluntario_id, participacao.id])


def responder(cliente, participacao, valor, fonte="voluntario"):
    variavel = proxima_variavel(participacao)
    return cliente.post(url(participacao), {"variavel": variavel.id, "valor": valor, "fonte": fonte})


def opcao(dominio, valor):
    return opcoes(dominio, valor)[0].id


@pytest.fixture
def estudo(pesquisadora):
    return novo_estudo(pesquisadora)


@pytest.fixture
def participacao(profissional, estudo):
    return nova_participacao(profissional, estudo)


def test_pergunta_primeiro_as_comuns_e_por_ultimo_as_sensiveis(estudo):
    criterio(estudo, "pessoa_com_deficiencia", "falso")
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "raca_cor", "esta_em", opcoes("raca_cor", "branca", "preta"))
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    ordem = [v.codigo for v in variaveis_da_coleta(estudo)]
    sensiveis = ["pessoa_com_deficiencia", "raca_cor"]
    assert set(ordem[-2:]) == set(sensiveis)
    assert set(ordem[:2]) == {"numero_filhos", "sexo_ao_nascer"}


def test_variavel_derivada_pergunta_as_origens(estudo):
    criterio(estudo, "idade_anos", "maior_igual", valor_numero=18)
    criterio(estudo, "faixa_etaria", "e", opcoes("faixa_etaria", "18_29"))
    criterio(estudo, "renda_per_capita", "menor_igual", valor_numero=1000)
    codigos = {v.codigo for v in variaveis_da_coleta(estudo)}
    assert codigos == {"data_nascimento", "renda_familiar_mensal", "pessoas_no_domicilio"}


def test_resposta_que_passa_e_gravada_e_segue_para_a_proxima(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    primeira = proxima_variavel(participacao)
    responder(cliente, participacao, 2 if primeira.codigo == "numero_filhos" else opcao("sexo_ao_nascer", "feminino"))
    assert ValorColetado.objects.filter(variavel=primeira, participacao=participacao).count() == 1
    assert proxima_variavel(participacao) != primeira
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.EM_COLETA


def test_todas_as_respostas_compativeis_concluem_a_coleta(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    responder(cliente, participacao, 2)
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.EM_COLETA
    resposta = cliente.get(url(participacao))
    assert "Coleta concluída" in resposta.content.decode()
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.CONCLUIDA
    assert participacao.criterio_reprovado is None


def test_estudo_sem_criterios_conclui_ao_abrir(cliente, participacao):
    cliente.get(url(participacao))
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.CONCLUIDA


def test_reprovacao_em_inclusao_elimina_e_nao_grava_a_resposta(cliente, participacao, estudo):
    regra = criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA
    assert participacao.criterio_reprovado == regra
    assert participacao.encerrada_em
    assert not ValorColetado.objects.exists()


def test_atender_exclusao_elimina(cliente, participacao, estudo):
    regra = criterio(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra=EXCLUSAO)
    responder(cliente, participacao, "sim")
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA
    assert participacao.criterio_reprovado == regra


def test_respostas_anteriores_ficam_e_so_a_que_reprovou_some(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    primeira = proxima_variavel(participacao)
    if primeira.codigo == "numero_filhos":
        responder(cliente, participacao, 2)
        responder(cliente, participacao, opcao("sexo_ao_nascer", "masculino"))
    else:
        responder(cliente, participacao, opcao("sexo_ao_nascer", "feminino"))
        responder(cliente, participacao, 0)
    gravadas = ValorColetado.objects.values_list("variavel__codigo", flat=True)
    assert list(gravadas) == [primeira.codigo]
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA


def test_eliminacao_pela_idade_calculada(cliente, participacao, estudo):
    from .teste_verificacao import nascido_ha

    regra = criterio(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    responder(cliente, participacao, nascido_ha(70).isoformat())
    participacao.refresh_from_db()
    assert participacao.criterio_reprovado == regra
    assert not ValorColetado.objects.exists()


def test_coleta_encerrada_nao_aceita_nova_resposta(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    cliente.post(url(participacao), {"variavel": 1, "valor": 5, "fonte": "voluntario"})
    assert not ValorColetado.objects.exists()


def test_resposta_de_outra_variavel_e_ignorada(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    cliente.post(url(participacao), {"variavel": 999999, "valor": 2, "fonte": "voluntario"})
    assert not ValorColetado.objects.exists()


def test_valor_fora_da_faixa_plausivel_nao_e_gravado_nem_elimina(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    responder(cliente, participacao, 500)
    participacao.refresh_from_db()
    assert not ValorColetado.objects.exists()
    assert participacao.situacao == Participacao.Situacao.EM_COLETA


def test_sensivel_vai_para_tabela_propria_e_e_auditado_sem_o_valor(cliente, participacao, estudo):
    criterio(estudo, "pessoa_com_deficiencia", "verdadeiro")
    responder(cliente, participacao, "sim")
    assert ValorSensivel.objects.count() == 1
    assert not ValorColetado.objects.exists()
    registro = RegistroAuditoria.objects.get(acao=RegistroAuditoria.Acao.SENSIVEL_RESPOSTA)
    assert "pessoa_com_deficiencia" in registro.objeto
    assert "sim" not in registro.objeto.split()


def test_variavel_comum_e_auditada_como_resposta_de_coleta(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    responder(cliente, participacao, 2)
    assert RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.COLETA_RESPOSTA).count() == 1
    assert not RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.SENSIVEL_RESPOSTA).exists()


def test_eliminacao_fica_na_auditoria(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    assert RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.COLETA_ELIMINACAO).count() == 1


def test_pesquisador_ve_o_criterio_que_eliminou(client, pesquisadora, cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    client.force_login(pesquisadora)
    pagina = client.get(reverse("estudos:detalhe", args=[estudo.id])).content.decode()
    assert "Voluntários eliminados na coleta" in pagina
    assert "filhos" in pagina
    assert participacao.voluntario.codigo_hmac[:8] in pagina


def test_ficha_do_profissional_mostra_a_participacao_encerrada_sem_dizer_eliminada(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    ficha = cliente.get(reverse("voluntarios:detalhe", args=[participacao.voluntario_id])).content.decode()
    assert "encerrada" in ficha
    assert "eliminada" not in ficha
