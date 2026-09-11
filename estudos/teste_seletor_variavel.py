import pytest
from django.urls import reverse

from autenticacao.models import Usuario
from catalogo.models import Categoria, Subcategoria, Variavel
from estudos.models import Criterio, Estudo

pytestmark = pytest.mark.django_db


@pytest.fixture
def pesquisadora():
    return Usuario.objects.create_user(
        "p@alunos.umc.br", "Pesquisadora Teste", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )


@pytest.fixture
def estudo(pesquisadora):
    return Estudo.objects.create(
        nome="Controle glicêmico", condicao="Diabetes tipo 2", pesquisador=pesquisadora
    )


@pytest.fixture
def cliente(client, pesquisadora):
    client.force_login(pesquisadora)
    return client


@pytest.fixture
def subcategoria_extra():
    categoria = Categoria.objects.create(codigo="TST", nome="Categoria de teste", ordem=9)
    return Subcategoria.objects.create(categoria=categoria, codigo="OBS", nome="Observações", ordem=1)


def buscar(cliente, estudo, **parametros):
    endereco = reverse("estudos:lista_variaveis", args=[estudo.id])
    return cliente.get(endereco, parametros).content.decode()


def test_abre_na_raiz_mostrando_as_categorias(cliente, estudo):
    html = buscar(cliente, estudo)

    assert "SOC Perfil sociodemográfico" in html
    assert "Escolaridade" not in html


def test_categoria_mostra_as_subcategorias(cliente, estudo):
    categoria = Categoria.objects.get(codigo="SOC")

    html = buscar(cliente, estudo, cat=categoria.id)

    assert "IDN Identificação básica" in html
    assert "FAM Composição familiar" in html
    assert "Escolaridade" not in html


def test_subcategoria_mostra_as_variaveis(cliente, estudo):
    subcategoria = Subcategoria.objects.get(codigo="IDN")

    html = buscar(cliente, estudo, sub=subcategoria.id)

    assert "Data de nascimento" in html
    assert "Escolaridade" not in html


def test_busca_por_nome(cliente, estudo):
    html = buscar(cliente, estudo, q="escolaridade")

    assert "Escolaridade" in html
    assert "Estado civil" not in html


def test_busca_sem_acento_encontra_nome_com_acento(cliente, estudo):
    html = buscar(cliente, estudo, q="familia")

    assert "Renda familiar mensal" in html


def test_busca_por_pedaco_do_codigo(cliente, estudo):
    html = buscar(cliente, estudo, q="renda_per")

    assert "Renda per capita" in html


def test_busca_por_codigo_escrito_com_espaco(cliente, estudo):
    html = buscar(cliente, estudo, q="menores no domicilio")

    assert "Moradores com menos de 18 anos" in html


def test_filtro_por_subcategoria(cliente, estudo):
    familia = Subcategoria.objects.get(codigo="FAM")

    html = buscar(cliente, estudo, sub=familia.id)

    assert "Estado civil" in html
    assert "Escolaridade" not in html


def test_chips_vem_do_banco_com_contagem(cliente, estudo):
    html = buscar(cliente, estudo, q="renda")

    assert "Domicílio, renda, escolaridade e ocupação" in html
    assert "Composição familiar" not in html


def test_texto_livre_fica_fora(cliente, estudo, subcategoria_extra):
    Variavel.objects.create(
        subcategoria=subcategoria_extra,
        codigo="observacao_social",
        nome="Observação social",
        tipo=Variavel.Tipo.TEXTO,
    )

    html = buscar(cliente, estudo, q="observacao")

    assert "Observação social" not in html
    assert "Nenhuma variável encontrada" in html


def test_derivada_aparece(cliente, estudo):
    html = buscar(cliente, estudo, q="idade")

    assert "Idade em anos completos" in html


def test_variavel_carrega_a_definicao(cliente, estudo):
    html = buscar(cliente, estudo, q="renda familiar")

    assert "Soma da renda de todos os moradores do domicílio" in html


def test_variavel_que_ja_e_criterio_nao_e_selecionavel(cliente, estudo):
    idade = Variavel.objects.get(codigo="idade_anos")
    Criterio.objects.create(estudo=estudo, variavel=idade, operador="maior_igual", valor_numero=18)

    html = buscar(cliente, estudo, q="idade")

    assert "já é critério" in html
    assert 'aria-disabled="true"' in html
    assert reverse("estudos:criar_criterio", args=[estudo.id, idade.id]) not in html


def test_busca_sem_resultado_oferece_proposta(cliente, estudo):
    html = buscar(cliente, estudo, q="hemoglobina")

    assert "Nenhuma variável encontrada" in html
    assert reverse("estudos:propor_variavel", args=[estudo.id]) in html


def test_profissional_nao_acessa_o_seletor(client, estudo):
    profissional = Usuario.objects.create_user(
        "t@alunos.umc.br", "Profissional Teste", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL
    )
    client.force_login(profissional)

    resposta = client.get(reverse("estudos:lista_variaveis", args=[estudo.id]))

    assert resposta.status_code == 403


def test_seletor_de_estudo_alheio_responde_404(client, estudo):
    outra = Usuario.objects.create_user(
        "o@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )
    client.force_login(outra)

    resposta = client.get(reverse("estudos:lista_variaveis", args=[estudo.id]))

    assert resposta.status_code == 404


def criar_criterio_de_data(cliente, estudo, dados):
    nascimento = Variavel.objects.get(codigo="data_nascimento")
    endereco = reverse("estudos:criar_criterio", args=[estudo.id, nascimento.id])
    return cliente.post(endereco, dados)


def test_data_com_ano_apenas_vira_periodo_inteiro(cliente, estudo):
    criar_criterio_de_data(cliente, estudo, {"operador": "depois", "precisao": "ano", "ano": "1990"})

    criterio = Criterio.objects.get()
    assert criterio.valor_data.isoformat() == "1990-12-31"
    assert criterio.enunciado == "Data de nascimento depois de 1990"


def test_antes_de_um_ano_usa_o_primeiro_dia(cliente, estudo):
    criar_criterio_de_data(cliente, estudo, {"operador": "antes", "precisao": "ano", "ano": "1990"})

    assert Criterio.objects.get().valor_data.isoformat() == "1990-01-01"


def test_data_com_mes_e_ano(cliente, estudo):
    criar_criterio_de_data(cliente, estudo, {"operador": "depois", "precisao": "mes", "mes_ano": "1990-03"})

    criterio = Criterio.objects.get()
    assert criterio.valor_data.isoformat() == "1990-03-31"
    assert criterio.enunciado == "Data de nascimento depois de 03/1990"


def test_data_completa(cliente, estudo):
    criar_criterio_de_data(
        cliente, estudo, {"operador": "antes", "precisao": "dia", "data": "1990-03-15"}
    )

    assert Criterio.objects.get().enunciado == "Data de nascimento antes de 15/03/1990"


def test_entre_dois_anos_cobre_as_pontas(cliente, estudo):
    criar_criterio_de_data(
        cliente, estudo, {"operador": "entre", "precisao": "ano", "ano": "1990", "ano_ate": "1995"}
    )

    criterio = Criterio.objects.get()
    assert criterio.valor_data.isoformat() == "1990-01-01"
    assert criterio.valor_data_ate.isoformat() == "1995-12-31"


def test_data_inexistente_no_calendario_e_recusada(cliente, estudo):
    resposta = criar_criterio_de_data(
        cliente, estudo, {"operador": "antes", "precisao": "dia", "data": "1990-02-31"}
    )

    assert "válida" in resposta.content.decode()
    assert Criterio.objects.count() == 0


def test_campo_vazio_para_a_precisao_escolhida(cliente, estudo):
    resposta = criar_criterio_de_data(cliente, estudo, {"operador": "antes", "precisao": "mes"})

    assert "Informe o mês e o ano." in resposta.content.decode()
    assert Criterio.objects.count() == 0


def test_formulario_usa_seletores_nativos(cliente, estudo):
    nascimento = Variavel.objects.get(codigo="data_nascimento")
    html = cliente.get(reverse("estudos:criar_criterio", args=[estudo.id, nascimento.id])).content.decode()

    assert 'type="date"' in html
    assert 'type="month"' in html
