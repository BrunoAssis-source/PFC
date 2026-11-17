import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from autenticacao.models import Usuario
from estudos.models import Estudo
from voluntarios import cpf
from voluntarios.models import Participacao, Voluntario

from .conftest import criterio, novo_estudo, opcoes
from .teste_verificacao import valor

Acao = RegistroAuditoria.Acao


def cpf_sintetico(numero):
    base = f"{100000000 + numero:09d}"
    base += str(cpf._digito(base, 10))
    return base + str(cpf._digito(base, 11))


@pytest.fixture
def estudo(pesquisadora):
    novo = novo_estudo(pesquisadora, "Estudo da tela")
    criterio(novo, "numero_filhos", "maior_igual", valor_numero=1)
    criterio(novo, "cuidador_de_dependente", "verdadeiro")
    return novo


@pytest.fixture
def origem(pesquisadora, profissional):
    return novo_estudo(pesquisadora, "Estudo de origem")


def voluntario(profissional, origem, numero, filhos=None, cuidador=None):
    numero_cpf = cpf_sintetico(numero)
    pessoa = Voluntario.objects.create(
        codigo_hmac=cpf.codigo(numero_cpf), cpf_cifrado=cpf.cifrar(numero_cpf), criado_por=profissional
    )
    participacao = Participacao.objects.create(
        voluntario=pessoa, estudo=origem, tcle_versao="1", registrado_por=profissional
    )
    valor(participacao, "sexo_ao_nascer", profissional, opcao=opcoes("sexo_ao_nascer", "feminino")[0])
    if filhos is not None:
        valor(participacao, "numero_filhos", profissional, valor_numero=filhos)
    if cuidador is not None:
        valor(participacao, "cuidador_de_dependente", profissional, valor_booleano=cuidador)
    return pessoa, numero_cpf


@pytest.fixture
def cliente(client, pesquisadora):
    client.force_login(pesquisadora)
    return client


def endereco(estudo):
    return reverse("estudos:classificacao", args=[estudo.id])


def codigos_por_bloco(resposta):
    return {rotulo: {linha["codigo"] for linha in linhas} for rotulo, linhas in resposta.context["grupos"]}


def test_visitante_vai_para_o_login(client, estudo):
    resposta = client.get(endereco(estudo))

    assert resposta.status_code == 302 and resposta.url.startswith(f"{reverse(settings.LOGIN_URL)}?next=")


def test_profissional_recebe_negativa_e_ela_fica_na_auditoria(client, profissional, estudo):
    client.force_login(profissional)

    assert client.get(endereco(estudo)).status_code == 403
    assert RegistroAuditoria.objects.filter(acao=Acao.ACESSO_NEGADO, usuario=profissional).exists()


def test_estudo_de_outra_pesquisadora_responde_404(client, estudo):
    outra = Usuario.objects.create_user(
        "outra@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )
    client.force_login(outra)

    assert client.get(endereco(estudo)).status_code == 404
    assert not RegistroAuditoria.objects.filter(acao=Acao.ESTUDO_CLASSIFICACAO).exists()


def test_consulta_do_dono_fica_na_auditoria(cliente, pesquisadora, estudo):
    assert cliente.get(endereco(estudo)).status_code == 200

    registro = RegistroAuditoria.objects.get(acao=Acao.ESTUDO_CLASSIFICACAO)
    assert registro.usuario == pesquisadora and registro.objeto == estudo.nome


@pytest.mark.parametrize("situacao", [Estudo.Situacao.RASCUNHO, Estudo.Situacao.ENCERRADO])
def test_estudo_fora_de_ativo_avisa_que_nao_ha_classificacao(cliente, estudo, situacao):
    estudo.situacao = situacao
    estudo.save()

    resposta = cliente.get(endereco(estudo))

    assert resposta.status_code == 200
    assert "só existe para estudo ativo" in resposta.content.decode()
    assert "grupos" not in resposta.context


def test_estudo_ativo_sem_criterios_avisa_em_vez_de_listar_todos_como_elegiveis(
    cliente, pesquisadora, profissional, origem
):
    vazio = novo_estudo(pesquisadora, "Sem critérios")
    voluntario(profissional, origem, 1)

    resposta = cliente.get(endereco(vazio))

    assert "não tem critérios" in resposta.content.decode()
    assert "grupos" not in resposta.context


def test_cada_voluntario_aparece_no_bloco_do_seu_estado(cliente, estudo, profissional, origem):
    elegivel, _ = voluntario(profissional, origem, 1, filhos=2, cuidador=True)
    inelegivel, _ = voluntario(profissional, origem, 2, filhos=0, cuidador=True)
    pendente, _ = voluntario(profissional, origem, 3, filhos=2)

    blocos = codigos_por_bloco(cliente.get(endereco(estudo)))

    assert blocos["Elegíveis"] == {elegivel.codigo_hmac[:8]}
    assert blocos["Inelegíveis"] == {inelegivel.codigo_hmac[:8]}
    assert blocos["Pendentes"] == {pendente.codigo_hmac[:8]}
    assert blocos["Em coleta"] == set()


def test_filtro_separa_quem_tem_participacao_no_estudo_de_quem_veio_de_outro(cliente, estudo, profissional, origem):
    deste, _ = voluntario(profissional, origem, 1, filhos=2, cuidador=True)
    de_outro, _ = voluntario(profissional, origem, 2, filhos=2, cuidador=True)
    Participacao.objects.create(voluntario=deste, estudo=estudo, tcle_versao="1", registrado_por=profissional)

    def listados(parametro):
        blocos = codigos_por_bloco(cliente.get(endereco(estudo), parametro))
        return set().union(*blocos.values())

    assert listados({}) == {deste.codigo_hmac[:8], de_outro.codigo_hmac[:8]}
    assert listados({"origem": "deste"}) == {deste.codigo_hmac[:8]}
    assert listados({"origem": "outros"}) == {de_outro.codigo_hmac[:8]}
    assert listados({"origem": "qualquer"}) == {deste.codigo_hmac[:8], de_outro.codigo_hmac[:8]}


def test_pagina_nao_mostra_cpf_nem_o_codigo_completo(cliente, estudo, profissional, origem):
    pessoa, numero_cpf = voluntario(profissional, origem, 1, filhos=0, cuidador=True)

    html = cliente.get(endereco(estudo)).content.decode()

    assert pessoa.codigo_hmac[:8] in html
    assert pessoa.codigo_hmac not in html
    assert numero_cpf not in html and pessoa.cpf_cifrado not in html


def test_numero_de_consultas_nao_cresce_com_o_numero_de_voluntarios(cliente, estudo, profissional, origem):
    def consultas():
        with CaptureQueriesContext(connection) as captura:
            assert cliente.get(endereco(estudo)).status_code == 200
        return len(captura)

    voluntario(profissional, origem, 1, filhos=2, cuidador=True)
    voluntario(profissional, origem, 2, filhos=0, cuidador=True)
    voluntario(profissional, origem, 3, filhos=2)
    com_tres = consultas()

    for numero in range(4, 14):
        voluntario(profissional, origem, numero, filhos=numero % 3, cuidador=numero % 2 == 0)

    assert consultas() == com_tres


def test_topo_diz_quando_foi_calculada_e_que_nao_e_gravada(cliente, estudo, profissional, origem):
    voluntario(profissional, origem, 1, filhos=2, cuidador=True)

    html = cliente.get(endereco(estudo)).content.decode()

    assert "Calculado em" in html and "Ele não é gravado" in html


def test_pagina_traz_so_uma_fatia_e_a_contagem_cobre_todas(cliente, estudo, profissional, origem):
    for numero in range(1, 27):
        voluntario(profissional, origem, numero, filhos=0, cuidador=True)
    voluntario(profissional, origem, 27, filhos=2, cuidador=True)

    primeira = cliente.get(endereco(estudo))
    segunda = cliente.get(endereco(estudo), {"pagina": "2"})

    # Os totais saem do banco e valem em qualquer página.
    for resposta in (primeira, segunda):
        assert dict(resposta.context["totais"])["Inelegíveis"] == 26
        assert dict(resposta.context["totais"])["Elegíveis"] == 1
        assert resposta.context["paginas"] == 2
    assert [len(linhas) for _, linhas in primeira.context["grupos"]] == [25, 0, 0, 0]
    # Inelegível vem antes de elegível, também na virada de página.
    assert [len(linhas) for _, linhas in segunda.context["grupos"]] == [1, 0, 0, 1]
    assert "Página 2 de 2" in segunda.content.decode()


def test_pagina_invalida_ou_alem_do_fim_cai_numa_pagina_que_existe(cliente, estudo, profissional, origem):
    for numero in range(1, 28):
        voluntario(profissional, origem, numero, filhos=0, cuidador=True)

    assert cliente.get(endereco(estudo), {"pagina": "abc"}).context["pagina"] == 1
    assert cliente.get(endereco(estudo), {"pagina": "0"}).context["pagina"] == 1
    assert cliente.get(endereco(estudo), {"pagina": "99"}).context["pagina"] == 2


def test_link_de_pagina_mantem_o_filtro_de_origem(cliente, estudo, profissional, origem):
    for numero in range(1, 28):
        voluntario(profissional, origem, numero, filhos=0, cuidador=True)

    html = cliente.get(endereco(estudo), {"origem": "outros"}).content.decode()

    assert "?origem=outros&pagina=2" in html
