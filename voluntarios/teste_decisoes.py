import threading

import pytest
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from autenticacao.models import Usuario
from estudos.models import Estudo
from voluntarios import cpf, decisoes
from voluntarios.models import DecisaoCandidato, Participacao, ValorColetado, ValorSensivel, Voluntario

from .conftest import criterio, novo_estudo, opcoes
from .teste_verificacao import valor

Acao = RegistroAuditoria.Acao
Decisao = DecisaoCandidato.Decisao


def cpf_sintetico(numero):
    base = f"{100000000 + numero:09d}"
    base += str(cpf._digito(base, 10))
    return base + str(cpf._digito(base, 11))


@pytest.fixture
def estudo(pesquisadora):
    novo = novo_estudo(pesquisadora, "Estudo das decisões")
    criterio(novo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(novo, "cuidador_de_dependente", "verdadeiro")
    return novo


@pytest.fixture
def origem(pesquisadora):
    return novo_estudo(pesquisadora, "Estudo de origem")


def pessoa(profissional, onde, numero, filhos=None, cuidador=None):
    """Voluntário sintético com as respostas dadas, coletadas no estudo onde."""
    numero_cpf = cpf_sintetico(numero)
    voluntario = Voluntario.objects.create(
        codigo_hmac=cpf.codigo(numero_cpf), cpf_cifrado=cpf.cifrar(numero_cpf), criado_por=profissional
    )
    participacao = Participacao.objects.create(
        voluntario=voluntario, estudo=onde, tcle_versao="1", registrado_por=profissional,
        situacao=Participacao.Situacao.CONCLUIDA,
    )
    valor(participacao, "sexo_ao_nascer", profissional, opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    if filhos is not None:
        valor(participacao, "numero_filhos", profissional, valor_numero=filhos)
    if cuidador is not None:
        valor(participacao, "cuidador_de_dependente", profissional, valor_booleano=cuidador)
    return voluntario


@pytest.fixture
def elegivel(profissional, origem, estudo):
    return pessoa(profissional, origem, 1, filhos=2, cuidador=True)


@pytest.fixture
def pendente(profissional, origem, estudo):
    return pessoa(profissional, origem, 2, filhos=2)


@pytest.fixture
def inelegivel(profissional, origem, estudo):
    return pessoa(profissional, origem, 3, filhos=0, cuidador=True)


def decisao_de(estudo, voluntario):
    return DecisaoCandidato.objects.filter(estudo=estudo, codigo_voluntario=voluntario.codigo_hmac).first()


def endereco(nome, estudo):
    return reverse(f"voluntarios:{nome}", args=[estudo.id])


def mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


def na_origem(voluntario, origem):
    return Participacao.objects.get(voluntario=voluntario, estudo=origem)


@pytest.fixture
def cliente(client, pesquisadora):
    client.force_login(pesquisadora)
    return client


def test_RF12_CA01_candidato_pendente_nao_e_incluido_ate_concluir_a_coleta(
    cliente, profissional, origem, estudo, pendente
):
    resposta = cliente.post(endereco("incluir_candidatos", estudo), {"voluntarios": [pendente.id]})

    assert resposta.status_code == 302
    assert any("pendente" in m for m in mensagens(resposta))
    assert decisao_de(estudo, pendente) is None
    assert not Participacao.objects.filter(voluntario=pendente, estudo=estudo).exists()

    valor(na_origem(pendente, origem), "cuidador_de_dependente", profissional, valor_booleano=True)
    cliente.post(endereco("incluir_candidatos", estudo), {"voluntarios": [pendente.id]})

    assert decisao_de(estudo, pendente).decisao == Decisao.INCLUIDO


def test_RF12_CA02_candidato_elegivel_incluido_fica_registrado_com_autor_e_data(
    cliente, pesquisadora, estudo, elegivel
):
    cliente.post(endereco("incluir_candidatos", estudo), {"voluntarios": [elegivel.id]})

    registro = decisao_de(estudo, elegivel)
    assert registro.decisao == Decisao.INCLUIDO
    assert registro.decidido_por == pesquisadora and registro.decidido_em is not None
    assert registro.classificacao_na_decisao == "elegivel"


def test_inclusao_em_lote_pula_quem_nao_e_elegivel_e_explica_o_motivo(
    pesquisadora, estudo, elegivel, pendente, inelegivel
):
    relatorio = decisoes.incluir(estudo, [elegivel.id, pendente.id, inelegivel.id], pesquisadora)

    assert relatorio["feitos"] == [elegivel.codigo_hmac[:8]]
    motivos = dict(relatorio["pulados"])
    assert "pendente" in motivos[pendente.codigo_hmac[:8]]
    assert "inelegível" in motivos[inelegivel.codigo_hmac[:8]]
    assert decisao_de(estudo, pendente) is None and decisao_de(estudo, inelegivel) is None


def test_inclusao_de_quem_veio_de_outro_estudo_cria_vinculo_reaproveitado_sem_tcle(pesquisadora, estudo, elegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    vinculo = Participacao.objects.get(voluntario=elegivel, estudo=estudo)
    assert vinculo.origem == Participacao.Origem.REAPROVEITADO and vinculo.tcle_versao == ""


def test_inclusao_de_quem_foi_coletado_no_proprio_estudo_mantem_a_participacao(profissional, pesquisadora, estudo):
    proprio = pessoa(profissional, estudo, 9, filhos=1, cuidador=True)

    decisoes.incluir(estudo, [proprio.id], pesquisadora)

    vinculo = Participacao.objects.get(voluntario=proprio, estudo=estudo)
    assert vinculo.origem == Participacao.Origem.COLETADO and vinculo.tcle_versao == "1"


def test_quem_deixou_de_ser_elegivel_antes_da_inclusao_e_pulado(pesquisadora, profissional, origem, estudo, elegivel):
    valor(na_origem(elegivel, origem), "numero_filhos", profissional, valor_numero=0)

    relatorio = decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    assert relatorio["feitos"] == [] and decisao_de(estudo, elegivel) is None


def test_incluido_que_deixa_de_ser_elegivel_continua_incluido_com_aviso(
    pesquisadora, profissional, origem, estudo, elegivel
):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)
    valor(na_origem(elegivel, origem), "numero_filhos", profissional, valor_numero=0)

    pagina = decisoes.candidatos(estudo, situacoes=["inelegivel"])

    assert decisao_de(estudo, elegivel).decisao == Decisao.INCLUIDO
    linha = pagina["linhas"][0]
    assert linha["classe"] == "inelegivel" and linha["mudou_desde_a_inclusao"] is True


def test_recusa_e_livre_para_qualquer_situacao_e_nao_apaga_nada(
    pesquisadora, estudo, elegivel, pendente, inelegivel
):
    relatorio = decisoes.recusar(estudo, [elegivel.id, pendente.id, inelegivel.id], pesquisadora)

    assert len(relatorio["feitos"]) == 3 and relatorio["pulados"] == []
    assert {decisao_de(estudo, v).classificacao_na_decisao for v in (elegivel, pendente, inelegivel)} == {
        "elegivel", "pendente", "inelegivel"
    }
    assert Voluntario.objects.count() == 3 and ValorColetado.objects.exists()


def test_recusado_vira_incluido_se_for_elegivel(pesquisadora, estudo, elegivel):
    decisoes.recusar(estudo, [elegivel.id], pesquisadora)

    relatorio = decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    assert relatorio["feitos"] == [elegivel.codigo_hmac[:8]]
    assert DecisaoCandidato.objects.filter(estudo=estudo).count() == 1
    assert decisao_de(estudo, elegivel).decisao == Decisao.INCLUIDO


def test_recusado_que_deixou_de_ser_elegivel_nao_vira_incluido(pesquisadora, profissional, origem, estudo, elegivel):
    decisoes.recusar(estudo, [elegivel.id], pesquisadora)
    valor(na_origem(elegivel, origem), "numero_filhos", profissional, valor_numero=0)

    relatorio = decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    assert relatorio["feitos"] == [] and decisao_de(estudo, elegivel).decisao == Decisao.RECUSADO


def test_incluido_vira_recusado_desfaz_o_vinculo_e_guarda_a_decisao_anterior_na_auditoria(
    pesquisadora, estudo, elegivel
):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    decisoes.recusar(estudo, [elegivel.id], pesquisadora)

    assert not Participacao.objects.filter(voluntario=elegivel, estudo=estudo).exists()
    assert Voluntario.objects.filter(pk=elegivel.pk).exists()
    registro = RegistroAuditoria.objects.get(acao=Acao.DECISAO_ALTERACAO)
    assert "Antes: incluido. Depois: recusado" in registro.objeto


def test_voluntario_sem_outro_estudo_tem_os_dados_apagados_ao_ser_recusado(
    pesquisadora, profissional, origem, estudo, elegivel
):
    codigo = elegivel.codigo_hmac
    sensivel = ValorColetado.objects.filter(codigo_voluntario=codigo).first()
    ValorSensivel.objects.create(
        codigo_voluntario=codigo, variavel=sensivel.variavel, valor_booleano=True, fonte="voluntario",
        participacao=na_origem(elegivel, origem), coletado_por=profissional,
    )
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)
    origem.situacao = Estudo.Situacao.ENCERRADO
    origem.save()

    decisoes.recusar(estudo, [elegivel.id], pesquisadora)

    assert not Voluntario.objects.filter(codigo_hmac=codigo).exists()
    assert not ValorColetado.objects.filter(codigo_voluntario=codigo).exists()
    assert not ValorSensivel.objects.filter(codigo_voluntario=codigo).exists()
    assert not Participacao.objects.filter(voluntario_id=elegivel.id).exists()
    assert DecisaoCandidato.objects.get(estudo=estudo, codigo_voluntario=codigo).decisao == Decisao.RECUSADO
    assert "Dados do voluntário apagados" in RegistroAuditoria.objects.get(acao=Acao.DECISAO_ALTERACAO).objeto


def test_voluntario_com_outro_estudo_ativo_mantem_os_dados_ao_ser_recusado(pesquisadora, origem, estudo, elegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    decisoes.recusar(estudo, [elegivel.id], pesquisadora)

    assert ValorColetado.objects.filter(codigo_voluntario=elegivel.codigo_hmac).exists()
    assert Participacao.objects.filter(voluntario=elegivel, estudo=origem).exists()


@pytest.mark.django_db(transaction=True)
def test_duas_inclusoes_ao_mesmo_tempo_geram_uma_so_decisao(pesquisadora, profissional, origem, estudo):
    candidato = pessoa(profissional, origem, 7, filhos=2, cuidador=True)
    resultados = []

    def incluir():
        try:
            resultados.append(decisoes.incluir(estudo, [candidato.id], pesquisadora))
        finally:
            connection.close()

    linhas = [threading.Thread(target=incluir) for _ in range(2)]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join()

    assert sorted(len(r["feitos"]) for r in resultados) == [0, 1]
    assert DecisaoCandidato.objects.filter(estudo=estudo).count() == 1
    assert Participacao.objects.filter(voluntario=candidato, estudo=estudo).count() == 1


def test_auditoria_registra_inclusao_e_recusa_sem_dado_pessoal(pesquisadora, estudo, elegivel, pendente):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)
    decisoes.recusar(estudo, [pendente.id], pesquisadora)

    inclusao = RegistroAuditoria.objects.get(acao=Acao.DECISAO_INCLUSAO)
    recusa = RegistroAuditoria.objects.get(acao=Acao.DECISAO_RECUSA)
    assert inclusao.usuario == pesquisadora and recusa.usuario == pesquisadora
    assert inclusao.objeto == f"{elegivel.codigo_hmac[:8]} em {estudo.nome}"
    for registro in (inclusao, recusa):
        assert elegivel.codigo_hmac not in registro.objeto and cpf_sintetico(1) not in registro.objeto


def test_meta_ultrapassada_so_avisa_e_nao_barra_a_inclusao(pesquisadora, profissional, origem, estudo, elegivel):
    estudo.participantes_necessarios = 1
    estudo.save()
    outro = pessoa(profissional, origem, 4, filhos=3, cuidador=True)

    relatorio = decisoes.incluir(estudo, [elegivel.id, outro.id], pesquisadora)

    assert len(relatorio["feitos"]) == 2
    assert relatorio["meta"] == {"incluidos": 2, "necessarios": 1, "acima": True}


def test_lista_de_candidatos_filtra_pagina_e_nao_expoe_cpf(pesquisadora, estudo, elegivel, pendente, inelegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    def ids(**filtros):
        return {linha["voluntario_id"] for linha in decisoes.candidatos(estudo, **filtros)["linhas"]}

    padrao = decisoes.candidatos(estudo)
    assert ids() == {elegivel.id}
    assert ids(situacoes=["elegivel", "pendente"]) == {elegivel.id, pendente.id}
    assert ids(situacoes=["inelegivel"]) == {inelegivel.id}
    assert ids(decisao="incluido") == {elegivel.id}
    assert ids(situacoes=["pendente"], decisao="sem") == {pendente.id}
    assert ids(origem="outros") == {elegivel.id}
    assert ids(origem="deste") == set()
    assert ids(situacoes=["pendente"], codigo=pendente.codigo_hmac[:6].upper()) == {pendente.id}
    assert ids(codigo="%") == set()
    paginada = decisoes.candidatos(estudo, situacoes=["elegivel", "pendente"], por_pagina=1, pagina=2)
    assert paginada["paginas"] == 2 and len(paginada["linhas"]) == 1
    texto = str(padrao)
    assert cpf_sintetico(1) not in texto and elegivel.codigo_hmac not in texto


def test_estudo_encerrado_so_permite_ler_as_decisoes(pesquisadora, estudo, elegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)
    estudo.situacao = Estudo.Situacao.ENCERRADO
    estudo.save()

    assert [l["decisao"] for l in decisoes.candidatos(estudo)["linhas"]] == ["incluido"]
    with pytest.raises(PermissionDenied):
        decisoes.recusar(estudo, [elegivel.id], pesquisadora)
    assert decisao_de(estudo, elegivel).decisao == Decisao.INCLUIDO


@pytest.mark.parametrize("nome", ["incluir_candidatos", "recusar_candidatos"])
class TestAcesso:
    def test_visitante_vai_para_o_login(self, client, estudo, nome):
        assert client.post(endereco(nome, estudo)).status_code == 302

    def test_profissional_recebe_403_e_a_negativa_fica_na_auditoria(self, client, profissional, estudo, elegivel, nome):
        client.force_login(profissional)

        assert client.post(endereco(nome, estudo), {"voluntarios": [elegivel.id]}).status_code == 403
        assert RegistroAuditoria.objects.filter(acao=Acao.ACESSO_NEGADO, usuario=profissional).exists()
        assert not DecisaoCandidato.objects.exists()

    def test_outro_pesquisador_recebe_404(self, client, estudo, elegivel, nome):
        outra = Usuario.objects.create_user(
            "outra@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
        )
        client.force_login(outra)

        assert client.post(endereco(nome, estudo), {"voluntarios": [elegivel.id]}).status_code == 404
        assert not DecisaoCandidato.objects.exists()

    def test_estudo_encerrado_recebe_403(self, cliente, estudo, elegivel, nome):
        estudo.situacao = Estudo.Situacao.ENCERRADO
        estudo.save()

        assert cliente.post(endereco(nome, estudo), {"voluntarios": [elegivel.id]}).status_code == 403
        assert not DecisaoCandidato.objects.exists()

    def test_get_nao_e_aceito(self, cliente, estudo, nome):
        assert cliente.get(endereco(nome, estudo)).status_code == 405


def test_tela_lista_candidatos_com_codigo_curto_e_sem_cpf(cliente, pesquisadora, estudo, elegivel, pendente, inelegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)

    resposta = cliente.get(endereco("candidatos", estudo))

    texto = resposta.content.decode()
    assert resposta.status_code == 200
    assert elegivel.codigo_hmac[:8] in texto
    assert pendente.codigo_hmac[:8] not in texto and inelegivel.codigo_hmac[:8] not in texto
    assert cpf_sintetico(1) not in texto and elegivel.codigo_hmac not in texto
    assert "Incluir selecionados" in texto and "Recusar selecionados" in texto


def test_tela_aplica_o_filtro_de_situacao(cliente, estudo, elegivel, pendente, inelegivel):
    resposta = cliente.get(endereco("candidatos", estudo), {"situacao": ["inelegivel"]})

    assert inelegivel.codigo_hmac[:8] in resposta.content.decode()
    assert elegivel.codigo_hmac[:8] not in resposta.content.decode()


def test_tela_mostra_o_aviso_de_situacao_mudada(cliente, pesquisadora, profissional, origem, estudo, elegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)
    valor(na_origem(elegivel, origem), "numero_filhos", profissional, valor_numero=0)

    resposta = cliente.get(endereco("candidatos", estudo), {"situacao": ["inelegivel"]})
    assert "Situação mudou desde a inclusão" in resposta.content.decode()


def test_tela_de_estudo_encerrado_e_so_leitura(cliente, pesquisadora, estudo, elegivel):
    decisoes.incluir(estudo, [elegivel.id], pesquisadora)
    estudo.situacao = Estudo.Situacao.ENCERRADO
    estudo.save()

    texto = cliente.get(endereco("candidatos", estudo)).content.decode()

    assert elegivel.codigo_hmac[:8] in texto
    assert "Incluir selecionados" not in texto and 'type="checkbox"' not in texto


def test_tela_de_rascunho_avisa_que_ainda_nao_ha_candidatos(cliente, estudo):
    estudo.situacao = Estudo.Situacao.RASCUNHO
    estudo.save()

    assert "quando o estudo estiver ativo" in cliente.get(endereco("candidatos", estudo)).content.decode()


def test_tela_nega_profissional_e_outro_pesquisador(client, profissional, estudo):
    client.force_login(profissional)
    assert client.get(endereco("candidatos", estudo)).status_code == 403

    outra = Usuario.objects.create_user(
        "outra@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )
    client.force_login(outra)
    assert client.get(endereco("candidatos", estudo)).status_code == 404


def test_estudo_sem_criterios_nao_inclui_ninguem(pesquisadora, profissional, origem):
    vazio = novo_estudo(pesquisadora, "Sem critérios")
    alguem = pessoa(profissional, origem, 5, filhos=1)

    relatorio = decisoes.incluir(vazio, [alguem.id], pesquisadora)

    assert relatorio["feitos"] == [] and "critérios" in relatorio["pulados"][0][1]


def test_tela_abre_so_com_elegiveis_e_marcar_dois_filtros_mostra_os_dois(cliente, estudo, elegivel, pendente):
    padrao = cliente.get(endereco("candidatos", estudo)).content.decode()
    ampliado = cliente.get(endereco("candidatos", estudo), {"situacao": ["elegivel", "pendente"]}).content.decode()

    assert pendente.codigo_hmac[:8] not in padrao
    assert elegivel.codigo_hmac[:8] in ampliado and pendente.codigo_hmac[:8] in ampliado
