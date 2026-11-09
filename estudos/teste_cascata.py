import pytest
from django.urls import reverse

from autenticacao.models import Usuario
from catalogo.models import OpcaoDominio
from estudos.conftest import opcoes, variavel
from estudos.forms import CriterioForm
from estudos.models import Criterio

pytestmark = pytest.mark.django_db


def endereco(nome, estudo, codigo):
    return reverse(f"estudos:{nome}", args=[estudo.id, variavel(codigo).id])


def estado(sigla):
    return OpcaoDominio.objects.get(dominio__codigo="uf", valor=sigla)


def listar(cliente, estudo, pai, codigo="municipio_residencia"):
    return cliente.get(endereco("opcoes_filhas", estudo, codigo), {"pai": pai})


def test_configuracao_de_municipio_pede_primeiro_o_estado(cliente, estudo):
    html = cliente.get(endereco("configurar_criterio", estudo, "municipio_residencia")).content.decode()

    assert "data-cascata" in html
    assert html.count("<option") == 28
    assert "São Paulo" in html and "Rio de Janeiro" in html


def test_configuracao_de_estado_e_uma_lista_comum(cliente, estudo):
    html = cliente.get(endereco("configurar_criterio", estudo, "uf_residencia")).content.decode()

    assert "data-cascata" not in html
    assert 'type="checkbox"' in html


def test_municipios_do_estado_escolhido_sao_listados(cliente, estudo):
    html = listar(cliente, estudo, estado("sp").id).content.decode()

    assert "Mogi das Cruzes (SP)" in html
    assert "Suzano (SP)" in html
    assert "(RJ)" not in html
    assert html.count('type="checkbox"') == 645


def test_lista_de_municipios_nao_tem_campo_nomeado(cliente, estudo):
    # A seleção vive nos campos ocultos criados pelo script, não nas caixas da lista.
    html = listar(cliente, estudo, estado("sp").id).content.decode()

    assert "name=" not in html


@pytest.mark.parametrize("pai", ["", "abc", "999999"])
def test_estado_invalido_responde_404(cliente, estudo, pai):
    assert listar(cliente, estudo, pai).status_code == 404


def test_pai_de_outro_dominio_responde_404(cliente, estudo):
    mogi = OpcaoDominio.objects.get(valor="3530607")

    assert listar(cliente, estudo, mogi.id).status_code == 404


def test_variavel_sem_dominio_superior_nao_tem_cascata(cliente, estudo):
    assert listar(cliente, estudo, estado("sp").id, "escolaridade").status_code == 404


def test_municipios_de_estados_diferentes_formam_um_criterio(cliente, estudo):
    escolhidos = [OpcaoDominio.objects.get(valor="3530607"), OpcaoDominio.objects.get(rotulo="Niterói (RJ)")]

    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, "municipio_residencia"),
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [o.id for o in escolhidos]},
    )

    assert resposta.status_code == 200
    criterio = Criterio.objects.get()
    assert criterio.frase == "Incluir participantes com município de residência: niterói (rj) ou mogi das cruzes (sp)"


def test_municipio_sem_escolha_pede_ao_menos_um(cliente, estudo):
    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, "municipio_residencia"),
        {"tipo_regra": "inclusao", "operador": "esta_em"},
    )

    assert resposta.status_code == 422
    assert "Escolha ao menos um valor." in resposta.content.decode()
    assert Criterio.objects.count() == 0


def test_municipio_de_variavel_errada_e_recusado(cliente, estudo):
    # O formulário só aceita opções do domínio da variável.
    estados = [estado("sp").id]
    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, "municipio_residencia"),
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": estados},
    )

    assert resposta.status_code == 422
    assert Criterio.objects.count() == 0


def test_criterio_de_estado(cliente, estudo):
    cliente.post(
        endereco("adicionar_criterio", estudo, "uf_residencia"),
        {"tipo_regra": "exclusao", "operador": "esta_em", "opcoes": [o.id for o in opcoes("uf", "sp", "rj")]},
    )

    assert Criterio.objects.get().frase == "Excluir participantes com estado de residência: rio de janeiro ou são paulo"


def test_formulario_nao_marca_todos_os_municipios_como_regra_de_todas():
    form = CriterioForm(
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [OpcaoDominio.objects.get(valor="3530607").id]},
        variavel=variavel("municipio_residencia"),
    )

    assert form.is_valid()


def rotas(estudo):
    codigo = variavel("municipio_residencia").id
    return reverse("estudos:opcoes_filhas", args=[estudo.id, codigo]) + f"?pai={estado('sp').id}"


def test_profissional_nao_lista_municipios(client, estudo):
    client.force_login(
        Usuario.objects.create_user("t@alunos.umc.br", "Profissional Teste", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL)
    )

    assert client.get(rotas(estudo)).status_code == 403


def test_estudo_alheio_nao_lista_municipios(client, estudo):
    client.force_login(
        Usuario.objects.create_user("o@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    )

    assert client.get(rotas(estudo)).status_code == 404


def test_visitante_vai_para_o_login_ao_listar_municipios(client, estudo):
    resposta = client.get(rotas(estudo))

    assert resposta.status_code == 302 and resposta.url.startswith("/?next=")
