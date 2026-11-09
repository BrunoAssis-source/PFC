import re

import pytest
from django.core import mail
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from voluntarios import cpf
from voluntarios.coleta import proxima_variavel, respostas_pendentes
from voluntarios.models import Participacao, PendenciaNotificada, ValorColetado, ValorSensivel, Voluntario
from voluntarios.pendencias import classificacao, pendentes, sincronizar_notificacoes

from .conftest import CPF_A, criterio, novo_estudo, opcoes
from .teste_verificacao import valor

Acao = RegistroAuditoria.Acao
MENSAGEM = "Coleta encerrada: este voluntário não é compatível com o estudo."


@pytest.fixture
def base(profissional, pesquisadora):
    """Voluntário com dados de um estudo anterior (sexo e filhos) e um estudo novo que exige uma variável a mais."""
    anterior = novo_estudo(pesquisadora, "Estudo anterior")
    voluntario = Voluntario.objects.create(
        codigo_hmac=cpf.codigo(CPF_A), cpf_cifrado=cpf.cifrar(CPF_A), criado_por=profissional
    )
    origem = Participacao.objects.create(
        voluntario=voluntario, estudo=anterior, tcle_versao="1", registrado_por=profissional,
        situacao=Participacao.Situacao.CONCLUIDA,
    )
    valor(origem, "sexo_ao_nascer", profissional, opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    valor(origem, "numero_filhos", profissional, valor_numero=2)

    novo = novo_estudo(pesquisadora, "Estudo novo")
    criterio(novo, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino"))
    regra = criterio(novo, "renda_familiar_mensal", "menor", valor_numero=3000)
    return voluntario, novo, regra


def url_coleta(participacao):
    return reverse("voluntarios:coleta", args=[participacao.voluntario_id, participacao.id])


def abrir_coleta_da_pendencia(cliente, voluntario, estudo):
    resposta = cliente.post(
        reverse("voluntarios:vincular", args=[voluntario.id]), {"estudo": estudo.id, "tcle": "on", "seguir": "coleta"}
    )
    return Participacao.objects.get(voluntario=voluntario, estudo=estudo), resposta


def responder(cliente, participacao, valor_resposta):
    variavel = proxima_variavel(participacao, respostas_pendentes(cliente.session, participacao))
    return cliente.post(url_coleta(participacao), {"variavel": variavel.id, "valor": valor_resposta, "fonte": "voluntario"})


def test_RF11_CA01_pendente_aparece_com_as_variaveis_faltantes_e_sem_o_criterio(cliente, base):
    voluntario, estudo, regra = base

    pagina = cliente.get(reverse("pendencias")).content.decode()

    assert f"Voluntário {voluntario.codigo_hmac[:8]}" in pagina
    assert "Estudo novo" in pagina
    assert "Renda familiar mensal" in pagina
    assert "Sexo ao nascer" not in pagina
    for proibido in (regra.frase, "3.000", "3000", "abaixo de", "Incluir", "Excluir", "elegível", "inelegível", "pendente"):
        assert proibido not in pagina


def test_RF11_CA01_a_tela_nao_mostra_cpf_nem_o_codigo_inteiro(cliente, base):
    voluntario, *_ = base

    pagina = cliente.get(reverse("pendencias")).content.decode()

    assert CPF_A not in pagina and voluntario.codigo_hmac not in pagina


def test_RF11_CA02_registrados_os_valores_faltantes_o_voluntario_sai_da_lista(cliente, base):
    voluntario, estudo, _ = base
    assert len(pendentes()) == 1

    participacao, _ = abrir_coleta_da_pendencia(cliente, voluntario, estudo)
    responder(cliente, participacao, 2000)

    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.CONCLUIDA
    assert pendentes() == []
    pagina = cliente.get(reverse("pendencias")).content.decode()
    assert voluntario.codigo_hmac[:8] not in pagina
    assert "Nenhuma pendência registrada" in pagina
    assert classificacao(voluntario.id, estudo.id)[(voluntario.id, estudo.id)] == "elegivel"


def test_coleta_da_pendencia_pede_so_a_variavel_que_falta(cliente, base):
    voluntario, estudo, _ = base

    participacao, resposta = abrir_coleta_da_pendencia(cliente, voluntario, estudo)

    assert resposta.status_code == 302 and resposta.url == url_coleta(participacao)
    pagina = cliente.get(url_coleta(participacao)).content.decode()
    assert "Renda familiar mensal" in pagina and "Sexo ao nascer" not in pagina
    assert ValorColetado.objects.filter(participacao=participacao).count() == 0


def test_valor_que_reprova_na_coleta_da_pendencia_encerra_com_a_mensagem_neutra(cliente, base):
    voluntario, estudo, _ = base
    participacao, _ = abrir_coleta_da_pendencia(cliente, voluntario, estudo)

    responder(cliente, participacao, 5000)

    participacao.refresh_from_db()
    assert participacao.situacao == Participacao.Situacao.ELIMINADA
    assert not ValorColetado.objects.filter(participacao=participacao).exists()
    final = cliente.get(url_coleta(participacao)).content.decode()
    assert MENSAGEM in final and "renda" not in final.lower()
    assert pendentes() == []
    assert classificacao(voluntario.id, estudo.id)[(voluntario.id, estudo.id)] == "inelegivel"


def test_mensagem_de_eliminacao_da_pendencia_e_igual_a_de_uma_coleta_nova(cliente, base, pesquisadora, profissional):
    voluntario, estudo, _ = base
    participacao, _ = abrir_coleta_da_pendencia(cliente, voluntario, estudo)
    responder(cliente, participacao, 5000)

    novo = nova_coleta_que_reprova(cliente, pesquisadora, profissional)

    limpar = lambda p: re.sub(r"/voluntarios/\d+/(participacoes/\d+/)?", "/voluntarios/N/",
                              re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", p))
    assert limpar(cliente.get(url_coleta(participacao)).content.decode()) == limpar(
        cliente.get(url_coleta(novo)).content.decode()
    )


def nova_coleta_que_reprova(cliente, pesquisadora, profissional):
    from .conftest import nova_participacao

    estudo = novo_estudo(pesquisadora, "Outro estudo")
    criterio(estudo, "renda_familiar_mensal", "menor", valor_numero=3000)
    participacao = nova_participacao(profissional, estudo, "11144477735")
    responder(cliente, participacao, 5000)
    return participacao


def test_variavel_sensivel_faltante_segue_as_regras_da_coleta(cliente, base, pesquisadora):
    voluntario, estudo, _ = base
    criterio(estudo, "pessoa_com_deficiencia", "falso")

    participacao, _ = abrir_coleta_da_pendencia(cliente, voluntario, estudo)
    primeira = proxima_variavel(participacao, {})
    assert primeira.codigo == "renda_familiar_mensal"
    responder(cliente, participacao, 2000)
    assert not ValorColetado.objects.filter(participacao=participacao).exists()

    segunda = proxima_variavel(participacao, respostas_pendentes(cliente.session, participacao))
    assert segunda.codigo == "pessoa_com_deficiencia"
    responder(cliente, participacao, "nao")

    assert ValorSensivel.objects.filter(participacao=participacao).count() == 1
    assert ValorColetado.objects.filter(participacao=participacao).count() == 1
    assert RegistroAuditoria.objects.filter(acao=Acao.SENSIVEL_RESPOSTA).exists()


def test_consulta_as_pendencias_e_auditada_sem_dados_pessoais(cliente, base, profissional):
    voluntario, *_ = base

    cliente.get(reverse("pendencias"))

    registro = RegistroAuditoria.objects.get(acao=Acao.PENDENCIAS_CONSULTA, usuario=profissional)
    assert registro.objeto == "1 pendências"
    assert voluntario.codigo_hmac[:8] not in registro.objeto


def test_coleta_dos_valores_faltantes_e_auditada_sem_dados_pessoais(cliente, base):
    voluntario, estudo, _ = base

    abrir_coleta_da_pendencia(cliente, voluntario, estudo)

    registro = RegistroAuditoria.objects.get(acao=Acao.PENDENCIA_COLETA)
    assert registro.objeto == f"{voluntario.codigo_hmac[:8]} em Estudo novo"
    for linha in RegistroAuditoria.objects.all():
        assert CPF_A not in linha.objeto


def test_pesquisador_recebe_negativa_na_lista_e_na_coleta_da_pendencia(client, pesquisadora, base):
    voluntario, estudo, _ = base
    client.force_login(pesquisadora)

    lista = client.get(reverse("pendencias"))
    coletar = client.post(
        reverse("voluntarios:vincular", args=[voluntario.id]), {"estudo": estudo.id, "tcle": "on", "seguir": "coleta"}
    )

    assert lista.status_code == 403 and coletar.status_code == 403
    assert not Participacao.objects.filter(voluntario=voluntario, estudo=estudo).exists()
    assert RegistroAuditoria.objects.filter(acao=Acao.ACESSO_NEGADO, usuario=pesquisadora).count() == 2


def test_anonimo_vai_para_o_login_na_lista_de_pendencias(client):
    resposta = client.get(reverse("pendencias"))
    assert resposta.status_code == 302 and resposta.url.startswith(reverse("login"))


def test_tcle_continua_obrigatorio_para_coletar_da_pendencia(cliente, base):
    voluntario, estudo, _ = base

    cliente.post(reverse("voluntarios:vincular", args=[voluntario.id]), {"estudo": estudo.id, "seguir": "coleta"})

    assert not Participacao.objects.filter(voluntario=voluntario, estudo=estudo).exists()


def test_coleta_de_estudo_que_deixou_de_ser_ativo_e_recusada(cliente, base):
    voluntario, estudo, _ = base
    participacao, _ = abrir_coleta_da_pendencia(cliente, voluntario, estudo)
    estudo.situacao = "encerrado"
    estudo.save()

    resposta = cliente.get(url_coleta(participacao))

    assert resposta.status_code == 302 and resposta.url == reverse("voluntarios:detalhe", args=[voluntario.id])


def test_RN29_nova_pendencia_avisa_o_profissional_so_com_estudo_e_codigo_curto(base, profissional):
    voluntario, estudo, _ = base

    sincronizar_notificacoes(estudo=estudo)

    assert len(mail.outbox) == 1
    aviso = mail.outbox[0]
    assert aviso.to == [profissional.email]
    assert estudo.nome in aviso.subject
    assert voluntario.codigo_hmac[:8] in aviso.body
    texto = aviso.subject + aviso.body
    for proibido in (CPF_A, voluntario.codigo_hmac, "3000", "renda", "sexo", "Renda", "abaixo"):
        assert proibido not in texto


def test_RN29_a_mesma_pendencia_nao_avisa_de_novo(base):
    _, estudo, _ = base

    sincronizar_notificacoes(estudo=estudo)
    sincronizar_notificacoes(estudo=estudo)

    assert len(mail.outbox) == 1


def test_RN29_pendencia_resolvida_e_que_volta_a_surgir_avisa_de_novo(cliente, base):
    voluntario, estudo, regra = base
    sincronizar_notificacoes(estudo=estudo)
    participacao, _ = abrir_coleta_da_pendencia(cliente, voluntario, estudo)
    responder(cliente, participacao, 2000)
    assert not PendenciaNotificada.objects.filter(voluntario=voluntario, estudo=estudo).exists()

    criterio(estudo, "cuidador_de_dependente", "verdadeiro")
    sincronizar_notificacoes(estudo=estudo)

    assert len([m for m in mail.outbox if "Nova pendência" in m.subject]) == 2


def test_RN29_criterio_novo_em_estudo_ativo_pela_tela_dispara_o_aviso(cliente_pesquisadora, base):
    voluntario, estudo, _ = base
    mail.outbox.clear()

    resposta = cliente_pesquisadora.post(
        reverse("estudos:adicionar_criterio", args=[estudo.id, __import__("catalogo.models", fromlist=["Variavel"]).Variavel.objects.get(codigo="numero_filhos").id]),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "1"},
    )

    assert resposta.status_code == 200
    assert len(mail.outbox) == 1 and estudo.nome in mail.outbox[0].subject


def test_RN29_falha_no_envio_nao_quebra_a_operacao_do_pesquisador(cliente_pesquisadora, base, monkeypatch, caplog):
    voluntario, estudo, _ = base
    monkeypatch.setattr("django.core.mail.message.EmailMessage.send", lambda self, *a, **k: (_ for _ in ()).throw(OSError("sem rede")))

    resposta = cliente_pesquisadora.post(
        reverse("estudos:adicionar_criterio", args=[estudo.id, __import__("catalogo.models", fromlist=["Variavel"]).Variavel.objects.get(codigo="numero_filhos").id]),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "1"},
    )

    assert resposta.status_code == 200
    assert "Falha ao enviar o aviso" in caplog.text


def test_RN29_conclusao_da_coleta_avisa_as_pendencias_que_surgem_em_outros_estudos(cliente, base, pesquisadora, profissional):
    from .conftest import nova_participacao

    outro = novo_estudo(pesquisadora, "Estudo com variavel extra")
    criterio(outro, "cuidador_de_dependente", "verdadeiro")
    estudo_novo = novo_estudo(pesquisadora, "Estudo de origem do novo")
    criterio(estudo_novo, "numero_filhos", "maior_igual", valor_numero=1)
    participacao = nova_participacao(profissional, estudo_novo, "11144477735")
    mail.outbox.clear()

    responder(cliente, participacao, 3)

    assunto = [m.subject for m in mail.outbox]
    assert any("Coleta concluída" in a for a in assunto)
    assert any(outro.nome in a and "pendência" in a for a in assunto)


@pytest.fixture
def cliente_pesquisadora(client, pesquisadora):
    client.force_login(pesquisadora)
    return client
