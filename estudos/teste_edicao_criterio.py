import re

import pytest
from django.urls import reverse

from autenticacao.models import Usuario
from catalogo.models import OpcaoDominio
from estudos.conftest import gravar, opcoes, variavel
from estudos.models import Criterio, Estudo

pytestmark = pytest.mark.django_db


def editar(criterio, nome="editar_criterio"):
    return reverse(f"estudos:{nome}", args=[criterio.estudo_id, criterio.id])


def tela(cliente, criterio):
    return cliente.get(editar(criterio)).content.decode()


def entradas(html, nome):
    return re.findall(rf'<input[^>]*name="{nome}"[^>]*>', html)


def marcados(html, nome):
    return [re.search(r'value="([^"]*)"', e).group(1) for e in entradas(html, nome) if " checked" in e]


def valor_do_campo(html, nome):
    return re.search(rf'<input[^>]*name="{nome}"[^>]*value="([^"]*)"', html).group(1)


def ids(codigo_do_dominio, *valores):
    return [str(o.id) for o in opcoes(codigo_do_dominio, *valores)]


def test_tela_de_edicao_avisa_que_a_variavel_nao_muda(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    html = tela(cliente, criterio)

    assert "Você está editando um critério do estudo" in html
    assert "Salvar alteração" in html
    assert 'data-modo="edicao"' in html
    assert f'action="{editar(criterio)}"' in html
    assert "data-cancelar" in html


def test_tela_de_adicionar_nao_tem_modo_de_edicao(cliente, estudo):
    html = cliente.get(reverse("estudos:configurar_criterio", args=[estudo.id, variavel("idade_anos").id])).content.decode()

    assert "data-modo" not in html
    assert "data-cancelar" not in html
    assert "Adicionar critério" in html


def test_edicao_numerica_vem_preenchida(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    html = tela(cliente, criterio)

    assert marcados(html, "operador") == ["entre"]
    assert marcados(html, "tipo_regra") == ["inclusao"]
    assert valor_do_campo(html, "valor_numero") == "18"
    assert valor_do_campo(html, "valor_numero_ate") == "65"


def test_edicao_de_exclusao_vem_com_excluir_marcado(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "menor", valor_numero=18, tipo_regra="exclusao")

    assert marcados(tela(cliente, criterio), "tipo_regra") == ["exclusao"]


def test_edicao_de_decimal_vem_sem_zeros_a_direita_e_com_ponto(cliente, estudo):
    criterio = gravar(estudo, "renda_familiar_mensal", "maior_igual", valor_numero="2500.50")

    assert valor_do_campo(tela(cliente, criterio), "valor_numero") == "2500.5"


def test_edicao_de_lista_vem_com_as_opcoes_marcadas(cliente, estudo):
    criterio = gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", "bissexual", "pansexual"))

    html = tela(cliente, criterio)

    assert sorted(marcados(html, "opcoes")) == sorted(ids("orientacao_sexual", "bissexual", "pansexual"))


def test_edicao_de_ordinal_vem_com_condicao_e_nivel(cliente, estudo):
    criterio = gravar(estudo, "escolaridade", "menor_igual", opcoes("escolaridade", "medio_completo"))

    html = tela(cliente, criterio)

    assert marcados(html, "operador") == ["menor_igual"]
    assert marcados(html, "opcoes") == ids("escolaridade", "medio_completo")


@pytest.mark.parametrize("operador", ["verdadeiro", "falso"])
def test_edicao_de_sim_ou_nao_vem_com_a_resposta(cliente, estudo, operador):
    criterio = gravar(estudo, "cuidador_de_dependente", operador)

    assert marcados(tela(cliente, criterio), "operador") == [operador]


def test_edicao_de_municipio_vem_com_as_etiquetas_dos_escolhidos(cliente, estudo):
    escolhidos = [OpcaoDominio.objects.get(valor="3530607"), OpcaoDominio.objects.get(valor="3552502")]
    criterio = gravar(estudo, "municipio_residencia", "esta_em", escolhidos)

    html = tela(cliente, criterio)

    assert sorted(re.findall(r'<input type="hidden" name="opcoes" value="(\d+)"', html)) == sorted(str(o.id) for o in escolhidos)
    assert "Mogi das Cruzes (SP)" in html and "Suzano (SP)" in html
    assert re.search(r'id="cascata-vazio"[^>]*hidden', html)


def test_edicao_sem_municipio_mostra_o_aviso_de_vazio(cliente, estudo):
    html = cliente.get(reverse("estudos:configurar_criterio", args=[estudo.id, variavel("municipio_residencia").id])).content.decode()

    assert not re.search(r'id="cascata-vazio"[^>]*hidden', html)
    assert "Nenhum município escolhido." in html


def test_editar_altera_o_mesmo_criterio_sem_criar_outro(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    resposta = cliente.post(
        editar(criterio), {"tipo_regra": "exclusao", "operador": "entre", "valor_numero": "20", "valor_numero_ate": "70"}
    )

    assert resposta.status_code == 200
    assert Criterio.objects.count() == 1
    criterio.refresh_from_db()
    assert criterio.tipo_regra == "exclusao"
    assert (criterio.valor_numero, criterio.valor_numero_ate) == (20, 70)
    assert "idade entre 20 e 70 anos" in resposta.content.decode()


def test_trocar_entre_por_outra_condicao_limpa_o_segundo_valor(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    cliente.post(editar(criterio), {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "21"})

    criterio.refresh_from_db()
    assert criterio.operador == "maior_igual" and criterio.valor_numero == 21
    assert criterio.valor_numero_ate is None
    assert criterio.frase == "Incluir participantes com idade de pelo menos 21 anos"


def test_editar_lista_troca_as_opcoes(cliente, estudo):
    criterio = gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", "bissexual"))

    cliente.post(
        editar(criterio),
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": ids("orientacao_sexual", "assexual", "outra")},
    )

    assert set(criterio.opcoes.all()) == set(opcoes("orientacao_sexual", "assexual", "outra"))


def test_editar_municipios_troca_a_selecao(cliente, estudo):
    criterio = gravar(estudo, "municipio_residencia", "esta_em", [OpcaoDominio.objects.get(valor="3530607")])
    novo = OpcaoDominio.objects.get(rotulo="Niterói (RJ)")

    cliente.post(editar(criterio), {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [novo.id]})

    assert list(criterio.opcoes.all()) == [novo]


def test_a_variavel_do_criterio_nao_muda_na_edicao(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    cliente.post(
        editar(criterio),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "30", "variavel": variavel("renda_familiar_mensal").id},
    )

    criterio.refresh_from_db()
    assert criterio.variavel == variavel("idade_anos")
    assert criterio.valor_numero == 30


@pytest.mark.parametrize(
    "dados, aviso",
    [
        ({"operador": "entre", "valor_numero": "18"}, "Informe os dois valores."),
        ({"operador": "maior_igual"}, "Informe o valor."),
        ({"operador": "maior_igual", "valor_numero": "500"}, "máximo plausível"),
    ],
)
def test_edicao_incompleta_responde_422_e_nao_altera_nada(cliente, estudo, dados, aviso):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    resposta = cliente.post(editar(criterio), {"tipo_regra": "exclusao", **dados})

    assert resposta.status_code == 422
    assert aviso in resposta.content.decode()
    criterio.refresh_from_db()
    assert criterio.tipo_regra == "inclusao"
    assert (criterio.operador, criterio.valor_numero, criterio.valor_numero_ate) == ("entre", 18, 65)


def test_editar_lista_para_todas_as_opcoes_e_recusado(cliente, estudo):
    criterio = gravar(estudo, "orientacao_sexual", "esta_em", opcoes("orientacao_sexual", "bissexual"))
    todas = [str(o.id) for o in OpcaoDominio.objects.filter(dominio__codigo="orientacao_sexual")]

    resposta = cliente.post(editar(criterio), {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": todas})

    assert resposta.status_code == 422
    assert "Esse critério inclui todos os participantes." in resposta.content.decode()
    assert set(criterio.opcoes.all()) == set(opcoes("orientacao_sexual", "bissexual"))


def test_edicao_devolve_a_lista_atualizada_com_resumo(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    html = cliente.post(
        editar(criterio), {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "21", "valor_numero_ate": "60"}
    ).content.decode()

    assert "Serão incluídos participantes com idade entre 21 e 60 anos." in html


def test_criterio_de_outro_estudo_da_mesma_pesquisadora_responde_404(cliente, pesquisadora, estudo):
    outro = Estudo.objects.create(nome="Outro", condicao="c", pesquisador=pesquisadora)
    criterio = gravar(outro, "idade_anos", "maior_igual", valor_numero=18)

    resposta = cliente.get(reverse("estudos:editar_criterio", args=[estudo.id, criterio.id]))

    assert resposta.status_code == 404


@pytest.mark.parametrize("metodo", ["put", "delete", "patch"])
def test_edicao_so_aceita_get_e_post(cliente, estudo, metodo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    assert getattr(cliente, metodo)(editar(criterio)).status_code == 405


def test_profissional_nao_edita_critério(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    client.force_login(
        Usuario.objects.create_user("t@alunos.umc.br", "Profissional Teste", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL)
    )

    assert client.get(editar(criterio)).status_code == 403
    assert client.post(editar(criterio), {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "99"}).status_code == 403
    criterio.refresh_from_db()
    assert criterio.valor_numero == 18


def test_estudo_alheio_nao_tem_criterio_editado(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    client.force_login(
        Usuario.objects.create_user("o@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    )

    assert client.get(editar(criterio)).status_code == 404
    assert client.post(editar(criterio), {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "99"}).status_code == 404
    criterio.refresh_from_db()
    assert criterio.valor_numero == 18


def test_visitante_vai_para_o_login_ao_editar(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    for resposta in (client.get(editar(criterio)), client.post(editar(criterio), {})):
        assert resposta.status_code == 302 and resposta.url.startswith("/?next=")


def test_lista_de_regras_tem_editar_e_a_confirmacao_de_remocao_escondida(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    html = cliente.get(reverse("estudos:criterios", args=[estudo.id])).content.decode()

    assert f'data-url="{editar(criterio)}"' in html
    assert "data-pedir-remocao" in html
    formulario = re.search(r'<form[^>]*class="remover-criterio regra-confirmacao"[^>]*>', html).group(0)
    assert f'action="{editar(criterio, "remover_criterio")}"' in formulario
    assert formulario.rstrip(">").endswith("hidden")
    assert "Sim, remover" in html and "data-cancelar-remocao" in html


def test_remover_continua_exigindo_post_mesmo_com_a_confirmacao_na_tela(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    assert cliente.get(editar(criterio, "remover_criterio")).status_code == 405
    assert Criterio.objects.count() == 1
