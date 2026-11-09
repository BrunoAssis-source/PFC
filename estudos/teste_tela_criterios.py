import pytest
from django.urls import reverse

from autenticacao.models import Usuario
from catalogo.models import OpcaoDominio
from estudos.conftest import gravar, opcoes, variavel
from estudos.models import Criterio

pytestmark = pytest.mark.django_db


def endereco(nome, estudo, *args):
    return reverse(f"estudos:{nome}", args=[estudo.id, *args])


def adicionar(cliente, estudo, codigo, dados):
    return cliente.post(endereco("adicionar_criterio", estudo, variavel(codigo).id), dados)


def previa(cliente, estudo, codigo, dados):
    return cliente.post(endereco("previa_criterio", estudo, variavel(codigo).id), dados).content.decode()


def test_pagina_mostra_a_arvore_sem_codigos_internos(cliente, estudo):
    html = cliente.get(endereco("criterios", estudo)).content.decode()

    assert "Perfil sociodemográfico" in html
    assert "Identificação básica" in html
    assert "Orientação sexual" in html
    assert "SOC" not in html and "IDN" not in html


def test_arvore_abre_com_todos_os_grupos_fechados(cliente, estudo):
    html = cliente.get(endereco("criterios", estudo)).content.decode()

    assert html.count('class="arvore-grupo"') >= 4
    assert 'arvore-grupo" open' not in html


def test_arvore_nao_lista_data_de_nascimento_nem_faixa_etaria(cliente, estudo):
    html = cliente.get(endereco("criterios", estudo)).content.decode()

    assert "Data de nascimento" not in html
    assert "Faixa etária" not in html


def test_busca_por_sinonimo_devolve_o_resultado_com_caminho(cliente, estudo):
    html = cliente.get(endereco("buscar_variaveis", estudo), {"q": "grau de instrução"}).content.decode()

    assert "Escolaridade" in html
    assert "Domicílio, renda, escolaridade e ocupação" in html


def test_busca_sem_resultado_oferece_propor_variavel(cliente, estudo):
    html = cliente.get(endereco("buscar_variaveis", estudo), {"q": "hemoglobina"}).content.decode()

    assert "Nenhuma variável encontrada" in html
    assert endereco("propor_variavel", estudo) in html


@pytest.mark.parametrize(
    "codigo, trecho",
    [
        ("idade_anos", 'name="valor_numero"'),
        ("orientacao_sexual", 'type="checkbox"'),
        ("escolaridade", 'type="radio" name="opcoes"'),
        ("cuidador_de_dependente", 'value="verdadeiro"'),
    ],
)
def test_configuracao_muda_conforme_o_tipo(cliente, estudo, codigo, trecho):
    resposta = cliente.get(endereco("configurar_criterio", estudo, variavel(codigo).id))

    assert resposta.status_code == 200
    assert trecho in resposta.content.decode()


@pytest.mark.parametrize("codigo", ["data_nascimento", "faixa_etaria"])
def test_variavel_fora_do_seletor_nao_abre_configuracao(cliente, estudo, codigo):
    resposta = cliente.get(endereco("configurar_criterio", estudo, variavel(codigo).id))

    assert resposta.status_code == 404


def test_previa_mostra_a_frase_quando_a_condicao_esta_completa(cliente, estudo):
    html = previa(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "65"})

    assert 'data-completo="1"' in html
    assert "Incluir participantes com idade entre 18 e 65 anos." in html


@pytest.mark.parametrize(
    "dados",
    [
        {"operador": "entre"},
        {"operador": "entre", "valor_numero": "18"},
        {"operador": "entre", "valor_numero_ate": "65"},
    ],
)
def test_previa_com_entre_pede_os_dois_valores(cliente, estudo, dados):
    html = previa(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", **dados})

    assert 'data-completo="0"' in html
    assert "Informe os dois valores." in html


@pytest.mark.parametrize("operador", ["maior_igual", "menor_igual", "igual"])
def test_previa_com_as_outras_condicoes_pede_o_valor(cliente, estudo, operador):
    html = previa(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": operador})

    assert 'data-completo="0"' in html
    assert "Informe o valor." in html
    assert "Informe os dois valores." not in html


def test_previa_formata_a_renda_em_reais(cliente, estudo):
    html = previa(
        cliente, estudo, "renda_familiar_mensal",
        {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "1000", "valor_numero_ate": "3000"},
    )

    assert "Incluir participantes com renda familiar entre R$ 1.000 e R$ 3.000." in html


def test_configuracao_mostra_a_faixa_da_renda_no_padrao_brasileiro(cliente, estudo):
    html = cliente.get(endereco("configurar_criterio", estudo, variavel("renda_familiar_mensal").id)).content.decode()

    assert "de R$ 0 a R$ 100.000" in html


def test_previa_nao_grava_nada(cliente, estudo):
    previa(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "18"})

    assert Criterio.objects.count() == 0


def test_adicionar_grava_o_criterio_e_devolve_a_lista(cliente, estudo):
    resposta = adicionar(
        cliente, estudo, "idade_anos",
        {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18", "valor_numero_ate": "65"},
    )

    assert resposta.status_code == 200
    criterio = Criterio.objects.get()
    assert criterio.estudo == estudo and criterio.tipo_regra == "inclusao"
    assert "idade entre 18 e 65 anos" in resposta.content.decode()


def test_adicionar_lista_grava_as_opcoes_escolhidas(cliente, estudo):
    escolhidas = opcoes("orientacao_sexual", "bissexual", "pansexual")

    adicionar(
        cliente, estudo, "orientacao_sexual",
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": [o.id for o in escolhidas]},
    )

    assert set(Criterio.objects.get().opcoes.all()) == set(escolhidas)


def test_adicionar_exclusao_aparece_no_resumo(cliente, estudo):
    resposta = adicionar(cliente, estudo, "cuidador_de_dependente", {"tipo_regra": "exclusao", "operador": "verdadeiro"})

    assert "Serão excluídos participantes com cuidador de dependente: sim." in resposta.content.decode()


def test_adicionar_incompleto_responde_422_e_nao_grava(cliente, estudo):
    resposta = adicionar(cliente, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "18"})

    assert resposta.status_code == 422
    assert "Informe os dois valores." in resposta.content.decode()
    assert Criterio.objects.count() == 0


def test_adicionar_lista_sem_opcao_nao_grava(cliente, estudo):
    resposta = adicionar(cliente, estudo, "orientacao_sexual", {"tipo_regra": "inclusao", "operador": "esta_em"})

    assert resposta.status_code == 422
    assert Criterio.objects.count() == 0


def test_adicionar_nao_aceita_get(cliente, estudo):
    resposta = cliente.get(endereco("adicionar_criterio", estudo, variavel("idade_anos").id))

    assert resposta.status_code == 405


def test_remover_apaga_so_o_criterio_pedido(cliente, estudo):
    manter = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    apagar = gravar(estudo, "cuidador_de_dependente", "verdadeiro", tipo_regra="exclusao")

    resposta = cliente.post(endereco("remover_criterio", estudo, apagar.id))

    assert resposta.status_code == 200
    assert list(Criterio.objects.all()) == [manter]


def test_remover_nao_aceita_get(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = cliente.get(endereco("remover_criterio", estudo, criterio.id))

    assert resposta.status_code == 405
    assert Criterio.objects.count() == 1


def test_detalhe_do_estudo_mostra_o_resumo(cliente, estudo):
    gravar(estudo, "idade_anos", "entre", valor_numero=18, valor_numero_ate=65)

    html = cliente.get(endereco("detalhe", estudo)).content.decode()

    assert "Serão incluídos participantes com idade entre 18 e 65 anos." in html


def rotas_da_tela(estudo, criterio):
    codigo = variavel("idade_anos").id
    return [
        ("get", endereco("criterios", estudo)),
        ("get", endereco("buscar_variaveis", estudo)),
        ("get", endereco("configurar_criterio", estudo, codigo)),
        ("post", endereco("previa_criterio", estudo, codigo)),
        ("post", endereco("adicionar_criterio", estudo, codigo)),
        ("post", endereco("remover_criterio", estudo, criterio.id)),
    ]


def test_profissional_recebe_403_em_toda_rota_da_tela(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    client.force_login(
        Usuario.objects.create_user("t@alunos.umc.br", "Profissional Teste", "Senha!2026x", perfil=Usuario.Perfil.PROFISSIONAL)
    )

    for metodo, rota in rotas_da_tela(estudo, criterio):
        assert getattr(client, metodo)(rota).status_code == 403, rota
    assert Criterio.objects.count() == 1


def test_estudo_de_outra_pesquisadora_responde_404_em_toda_rota(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    client.force_login(
        Usuario.objects.create_user("o@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    )

    for metodo, rota in rotas_da_tela(estudo, criterio):
        assert getattr(client, metodo)(rota).status_code == 404, rota
    assert Criterio.objects.count() == 1


def test_outra_pesquisadora_nao_adiciona_criterio_no_estudo_alheio(client, estudo):
    client.force_login(
        Usuario.objects.create_user("o@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    )

    adicionar(client, estudo, "idade_anos", {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "18"})

    assert Criterio.objects.count() == 0


def test_visitante_vai_para_o_login_em_toda_rota(client, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    for metodo, rota in rotas_da_tela(estudo, criterio):
        resposta = getattr(client, metodo)(rota)
        assert resposta.status_code == 302 and resposta.url.startswith("/?next="), rota
    assert Criterio.objects.count() == 1


def marcadas(codigo_do_dominio):
    return [opcao.id for opcao in OpcaoDominio.objects.filter(dominio__codigo=codigo_do_dominio)]


def test_previa_avisa_quando_todas_as_opcoes_estao_marcadas(cliente, estudo):
    html = previa(
        cliente, estudo, "orientacao_sexual",
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": marcadas("orientacao_sexual")},
    )

    assert 'data-completo="0"' in html
    assert "Esse critério inclui todos os participantes." in html


def test_previa_de_exclusao_avisa_que_exclui_todos(cliente, estudo):
    html = previa(
        cliente, estudo, "orientacao_sexual",
        {"tipo_regra": "exclusao", "operador": "esta_em", "opcoes": marcadas("orientacao_sexual")},
    )

    assert "Esse critério exclui todos os participantes." in html


def test_adicionar_com_todas_as_opcoes_marcadas_nao_grava(cliente, estudo):
    resposta = adicionar(
        cliente, estudo, "orientacao_sexual",
        {"tipo_regra": "inclusao", "operador": "esta_em", "opcoes": marcadas("orientacao_sexual")},
    )

    assert resposta.status_code == 422
    assert "Esse critério inclui todos os participantes." in resposta.content.decode()
    assert Criterio.objects.count() == 0


def test_botao_todas_aparece_com_tres_ou_mais_opcoes(cliente, estudo):
    html = cliente.get(endereco("configurar_criterio", estudo, variavel("orientacao_sexual").id)).content.decode()

    assert 'data-marcar="todas"' in html
    assert 'data-marcar="limpar"' in html


def test_botao_todas_some_com_so_duas_opcoes(cliente, estudo):
    html = cliente.get(endereco("configurar_criterio", estudo, variavel("zona_residencia").id)).content.decode()

    assert 'data-marcar="todas"' not in html
    assert 'data-marcar="limpar"' in html


def abrir_variavel(cliente, estudo, codigo):
    return cliente.get(endereco("criterios", estudo), {"variavel": variavel(codigo).id}).content.decode()


def test_variavel_vinda_do_link_abre_so_o_grupo_dela(cliente, estudo):
    html = abrir_variavel(cliente, estudo, "estado_civil")

    assert html.count('arvore-grupo" open') == 1
    grupo_aberto = html.split('arvore-grupo" open')[1].split("</details>")[0]
    assert "Estado civil" in grupo_aberto
    assert "Orientação sexual" not in grupo_aberto


def test_variavel_vinda_do_link_fica_marcada_e_com_a_configuracao_pedida(cliente, estudo):
    html = abrir_variavel(cliente, estudo, "estado_civil")
    destino = endereco("configurar_criterio", estudo, variavel("estado_civil").id)

    assert f'data-configuracao-inicial="{destino}"' in html
    assert html.count('aria-current="true"') == 1


@pytest.mark.parametrize("variavel_id", ["999999", "abc", ""])
def test_link_com_variavel_invalida_nao_abre_nada(cliente, estudo, variavel_id):
    html = cliente.get(endereco("criterios", estudo), {"variavel": variavel_id}).content.decode()

    assert "data-configuracao-inicial" not in html
    assert 'arvore-grupo" open' not in html


def test_link_com_variavel_fora_do_seletor_nao_abre_nada(cliente, estudo):
    html = abrir_variavel(cliente, estudo, "data_nascimento")

    assert "data-configuracao-inicial" not in html


def test_resultado_da_busca_aponta_para_o_mesmo_botao_da_arvore(cliente, estudo):
    # O script leva o pesquisador da busca ao grupo na árvore procurando o botão pelo endereço.
    destino = endereco("configurar_criterio", estudo, variavel("escolaridade").id)
    arvore = cliente.get(endereco("criterios", estudo)).content.decode()
    busca = cliente.get(endereco("buscar_variaveis", estudo), {"q": "escolaridade"}).content.decode()

    assert f'data-url="{destino}"' in arvore
    assert f'data-url="{destino}"' in busca
