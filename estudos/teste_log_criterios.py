import pytest
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from autenticacao.models import Usuario
from catalogo.models import OpcaoDominio
from estudos.conftest import gravar, variavel
from estudos.models import Criterio

pytestmark = pytest.mark.django_db

Acao = RegistroAuditoria.Acao
ACOES_DE_CRITERIO = [Acao.CRITERIO_ADICAO, Acao.CRITERIO_EDICAO, Acao.CRITERIO_REMOCAO]


def registros(*acoes):
    return list(RegistroAuditoria.objects.filter(acao__in=acoes or ACOES_DE_CRITERIO).order_by("id"))


def adicionar(cliente, estudo, codigo, dados):
    return cliente.post(reverse("estudos:adicionar_criterio", args=[estudo.id, variavel(codigo).id]), dados)


def editar(cliente, criterio, dados):
    return cliente.post(reverse("estudos:editar_criterio", args=[criterio.estudo_id, criterio.id]), dados)


def remover(cliente, criterio):
    return cliente.post(reverse("estudos:remover_criterio", args=[criterio.estudo_id, criterio.id]))


def test_adicionar_registra_usuario_estudo_frase_e_ip(cliente, estudo, pesquisadora):
    adicionar(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "65"})

    [registro] = registros()
    assert registro.acao == Acao.CRITERIO_ADICAO
    assert registro.usuario == pesquisadora
    assert registro.objeto == "Controle glicêmico. Incluir participantes com idade entre 18 e 65 anos"
    assert registro.ip == "127.0.0.1"
    assert registro.criado_em is not None


def test_adicionar_incompleto_nao_registra(cliente, estudo):
    adicionar(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18"})

    assert registros() == []


def test_editar_registra_a_frase_antes_e_depois(cliente, estudo, pesquisadora):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    editar(cliente, criterio, {"tipo_regra": "exclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "70"})

    [registro] = registros()
    assert registro.acao == Acao.CRITERIO_EDICAO
    assert registro.usuario == pesquisadora
    assert registro.objeto == (
        "Controle glicêmico. Antes: Incluir participantes com idade entre 18 e 65 anos. "
        "Depois: Excluir participantes com idade entre 18 e 70 anos"
    )


def test_editar_lista_registra_as_opcoes_antes_e_depois(cliente, estudo):
    criterio = gravar(estudo, "orientacao_sexual", "esta_em", OpcaoDominio.objects.filter(valor="bissexual"))
    nova = OpcaoDominio.objects.get(valor="assexual", dominio__codigo="orientacao_sexual")

    editar(cliente, criterio, {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [nova.id]})

    [registro] = registros()
    assert "Antes: Incluir participantes com orientação sexual: bissexual." in registro.objeto
    assert "Depois: Incluir participantes com orientação sexual: assexual" in registro.objeto


def test_editar_sem_mudar_nada_nao_registra(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    resposta = editar(cliente, criterio, {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "65"})

    assert resposta.status_code == 200
    assert registros() == []


def test_editar_invalido_nao_registra(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    editar(cliente, criterio, {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18"})

    assert registros() == []


def test_registro_guarda_texto_maior_que_150_caracteres(cliente, estudo):
    # O campo antigo cortava em 150, e a frase de uma lista de municípios passa disso.
    muitos = list(OpcaoDominio.objects.filter(dominio__codigo="municipio", pai__valor="sp")[:15])
    criterio = gravar(estudo, "municipio_residencia", "esta_em", muitos[:1])

    editar(cliente, criterio, {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [m.id for m in muitos]})

    [registro] = registros()
    assert len(registro.objeto) > 300
    assert registro.objeto.endswith(muitos[-1].rotulo.lower())


def test_remover_registra_a_frase_do_criterio_apagado(cliente, estudo, pesquisadora):
    criterio = gravar(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra="exclusao")

    remover(cliente, criterio)

    [registro] = registros()
    assert registro.acao == Acao.CRITERIO_REMOCAO
    assert registro.usuario == pesquisadora
    assert registro.objeto == "Controle glicêmico. Excluir participantes com cuidador de dependente: sim"
    assert Criterio.objects.count() == 0


def test_remover_criterio_inexistente_nao_registra(cliente, estudo):
    resposta = cliente.post(reverse("estudos:remover_criterio", args=[estudo.id, 999999]))

    assert resposta.status_code == 404
    assert registros() == []


def tentar_tudo(cliente, estudo, criterio):
    dados = {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "30"}
    cliente.post(reverse("estudos:editar_criterio", args=[estudo.id, criterio.id]), dados)
    cliente.post(reverse("estudos:remover_criterio", args=[estudo.id, criterio.id]))
    cliente.post(reverse("estudos:adicionar_criterio", args=[estudo.id, variavel("idade_anos").id]), dados)


def test_visitante_nao_gera_registro_de_criterio(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    tentar_tudo(client, estudo, criterio)

    assert registros() == []
    assert Criterio.objects.get().valor_numero == 18


def test_profissional_nao_gera_registro_de_criterio(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    client.force_login(
        Usuario.objects.create_user("t@alunos.umc.br", "Profissional Teste", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL)
    )

    tentar_tudo(client, estudo, criterio)

    assert registros() == []
    assert Criterio.objects.get().valor_numero == 18


def test_tela_de_auditoria_mostra_as_tres_acoes_ao_administrador(cliente, client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    adicionar(cliente, estudo, "cuidador_de_dependente", {"tipo_regra": "inclusao", "operador": "verdadeiro"})
    editar(cliente, criterio, {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "21"})
    remover(cliente, criterio)
    cliente.logout()
    admin = Usuario.objects.create_user("a@alunos.umc.br", "Administrador Teste", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    admin.is_staff = True
    admin.save()
    client.force_login(admin)

    html = client.get(reverse("auditoria:listar")).content.decode()

    for texto in ("adição de critério", "edição de critério", "remoção de critério"):
        assert texto in html
    assert "Antes: Incluir participantes com idade de pelo menos 18 anos" in html
