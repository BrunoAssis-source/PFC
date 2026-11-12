import pytest
from django.core import mail
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from estudos.models import Criterio
from voluntarios.coleta import proxima_variavel, respostas_pendentes, variaveis_da_coleta
from voluntarios.models import Participacao, ValorColetado, ValorSensivel

from .conftest import CPF_A, criterio, nova_participacao, novo_estudo, opcoes

EXCLUSAO = Criterio.TipoRegra.EXCLUSAO


def url(participacao):
    return reverse("voluntarios:coleta", args=[participacao.voluntario_id, participacao.id])


def responder(cliente, participacao, valor, fonte="voluntario"):
    pendentes = respostas_pendentes(cliente.session, participacao)
    variavel = proxima_variavel(participacao, pendentes)
    return cliente.post(url(participacao), {"variavel": variavel.id, "valor": valor, "fonte": fonte})


def opcao(dominio, valor):
    return opcoes(dominio, valor)[0].id


def responder_por_codigo(cliente, participacao, respostas):
    """Responde cada passo até a coleta terminar. Antes do último passo nada pode estar gravado."""
    while True:
        participacao.refresh_from_db()
        if participacao.situacao != Participacao.Situacao.EM_COLETA:
            return
        variavel = proxima_variavel(participacao, respostas_pendentes(cliente.session, participacao))
        cliente.post(url(participacao), {"variavel": variavel.id, "valor": respostas[variavel.codigo], "fonte": "voluntario"})
        participacao.refresh_from_db()
        if participacao.situacao == Participacao.Situacao.EM_COLETA:
            assert nada_gravado() and not mail.outbox


def nada_gravado():
    return not ValorColetado.objects.exists() and not ValorSensivel.objects.exists()


@pytest.fixture
def estudo(pesquisadora):
    return novo_estudo(pesquisadora)


@pytest.fixture
def participacao(profissional, estudo):
    return nova_participacao(profissional, estudo)


def test_pergunta_primeiro_as_comuns_e_por_ultimo_as_sensiveis(participacao, estudo):
    criterio(estudo, "pessoa_com_deficiencia", "falso")
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "raca_cor", "esta_em", opcoes("raca_cor", "branca", "preta"))
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    ordem = [v.codigo for v in variaveis_da_coleta(participacao)]
    assert set(ordem[-2:]) == {"pessoa_com_deficiencia", "raca_cor"}
    assert set(ordem[:2]) == {"numero_filhos", "sexo_ao_nascer"}


def test_variavel_derivada_pergunta_as_origens(participacao, estudo):
    criterio(estudo, "idade_anos", "maior_igual", valor_numero=18)
    criterio(estudo, "renda_per_capita", "menor_igual", valor_numero=1000)
    codigos = {v.codigo for v in variaveis_da_coleta(participacao)}
    assert codigos == {"data_nascimento", "renda_familiar_mensal", "pessoas_no_domicilio"}


def test_RF09_RN24_resposta_que_passa_so_avanca_e_nada_e_gravado(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    primeira = proxima_variavel(participacao, {})
    responder(cliente, participacao, 2 if primeira.codigo == "numero_filhos" else opcao("sexo_ao_nascer", "feminino"))
    assert nada_gravado()
    assert proxima_variavel(participacao, respostas_pendentes(cliente.session, participacao)) != primeira
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.EM_COLETA


def test_RF09_CA01_renda_acima_do_limite_interrompe_e_nao_grava_nenhum_valor(cliente, participacao, estudo):
    regra = criterio(estudo, "renda_familiar_mensal", "menor", valor_numero=3000)
    responder(cliente, participacao, 5000)
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA
    assert participacao.criterio_reprovado == regra
    assert nada_gravado()


def test_RF09_RN24_reprovar_depois_de_aprovar_descarta_tambem_as_respostas_anteriores(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    primeira = proxima_variavel(participacao, {})
    if primeira.codigo == "numero_filhos":
        responder(cliente, participacao, 2)
        responder(cliente, participacao, opcao("sexo_ao_nascer", "masculino"))
    else:
        responder(cliente, participacao, opcao("sexo_ao_nascer", "feminino"))
        responder(cliente, participacao, 0)
    assert nada_gravado()
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA
    assert respostas_pendentes(cliente.session, participacao) == {}


def test_RF09_CA02_criterios_atendidos_gravam_os_valores_e_notificam_o_pesquisador(
    cliente, participacao, estudo, pesquisadora
):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(estudo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    responder_por_codigo(
        cliente, participacao, {"numero_filhos": 2, "sexo_ao_nascer": opcao("sexo_ao_nascer", "feminino")}
    )

    assert ValorColetado.objects.count() == 2
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.CONCLUIDA
    assert participacao.criterio_reprovado is None
    assert len(mail.outbox) == 1
    aviso = mail.outbox[0]
    assert aviso.to == [pesquisadora.email]
    assert estudo.nome in aviso.subject
    assert participacao.voluntario.codigo_hmac[:8] in aviso.body


def test_RF09_CA02_email_nao_leva_cpf_nem_valores(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "igual", valor_numero=7)
    responder(cliente, participacao, 7)
    corpo = mail.outbox[0].subject + mail.outbox[0].body
    assert CPF_A not in corpo
    assert "7" not in corpo.replace(participacao.voluntario.codigo_hmac[:8], "").replace(estudo.nome, "")
    assert "filhos" not in corpo.lower()


def test_eliminacao_nao_envia_email(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    assert not mail.outbox


def test_RNF10_falha_no_email_nao_desfaz_a_coleta(cliente, participacao, estudo, monkeypatch, caplog):
    def falhar(self, *args, **kwargs):
        raise OSError("sem rede")

    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", falhar)
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    responder(cliente, participacao, 2)
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.CONCLUIDA
    assert ValorColetado.objects.count() == 1
    assert "Falha ao enviar o aviso" in caplog.text


def test_estudo_sem_criterios_conclui_ao_abrir(cliente, participacao):
    cliente.get(url(participacao))
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.CONCLUIDA


def test_atender_exclusao_elimina(cliente, participacao, estudo):
    regra = criterio(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra=EXCLUSAO)
    responder(cliente, participacao, "sim")
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA
    assert participacao.criterio_reprovado == regra


def test_eliminacao_pela_idade_calculada(cliente, participacao, estudo):
    from .teste_verificacao import nascido_ha

    regra = criterio(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)
    responder(cliente, participacao, nascido_ha(70).isoformat())
    participacao.refresh_from_db()
    assert participacao.criterio_reprovado == regra
    assert nada_gravado()


def test_depois_de_um_ano_trata_o_ultimo_dia_do_periodo(cliente, participacao, estudo):
    from datetime import date

    criterio(estudo, "data_nascimento", "depois", valor_data=date(1990, 12, 31), precisao="ano")
    responder(cliente, participacao, "1990-12-31")
    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA

    outra = nova_participacao(participacao.registrado_por, estudo, "11144477735")
    responder(cliente, outra, "1991-01-01")
    outra.refresh_from_db()
    assert outra.situacao == Participacao.Situacao.CONCLUIDA


def test_coleta_encerrada_nao_aceita_nova_resposta(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    cliente.post(url(participacao), {"variavel": 1, "valor": 5, "fonte": "voluntario"})
    assert nada_gravado()


def test_resposta_de_outra_variavel_e_ignorada(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    cliente.post(url(participacao), {"variavel": 999999, "valor": 2, "fonte": "voluntario"})
    assert respostas_pendentes(cliente.session, participacao) == {}


def test_valor_fora_da_faixa_plausivel_nao_avanca_nem_elimina(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    responder(cliente, participacao, 500)
    participacao.refresh_from_db()
    assert nada_gravado()
    assert participacao.situacao == Participacao.Situacao.EM_COLETA
    assert respostas_pendentes(cliente.session, participacao) == {}


def test_sensivel_vai_para_tabela_propria_ao_concluir_e_e_auditado_sem_o_valor(cliente, participacao, estudo):
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


def test_eliminacao_fica_na_auditoria_sem_valores(cliente, participacao, estudo):
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=3)
    responder(cliente, participacao, 1)
    registro = RegistroAuditoria.objects.get(acao=RegistroAuditoria.Acao.COLETA_ELIMINACAO)
    assert registro.objeto == f"{participacao.voluntario.codigo_hmac[:8]} em {estudo.nome}"


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
