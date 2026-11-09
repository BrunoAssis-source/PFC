import pytest
from django.urls import reverse

from autenticacao.models import Usuario
from estudos.conftest import gravar, variavel
from estudos.models import Criterio, Estudo

pytestmark = pytest.mark.django_db


def endereco(nome, estudo, *args):
    return reverse(f"estudos:{nome}", args=[estudo.id, *args])


def test_RF04_CA01_estudo_cadastrado_com_a_situacao_padrao_aparece_como_rascunho(cliente):
    formulario = cliente.get(reverse("estudos:criar")).context["form"]
    padrao = formulario["situacao"].value()
    assert padrao == Estudo.Situacao.RASCUNHO

    cliente.post(
        reverse("estudos:criar"),
        {"nome": "Estudo novo", "condicao": "Condição", "descricao": "", "participantes_necessarios": "", "situacao": padrao},
    )

    lista = cliente.get(reverse("estudos:listar"))
    assert lista.status_code == 200
    estudo = Estudo.objects.get(nome="Estudo novo")
    assert estudo.situacao == Estudo.Situacao.RASCUNHO
    assert "Estudo novo" in lista.content.decode()
    assert lista.context["total_rascunhos"] == 1


def test_RF04_CA02_estudo_de_outro_pesquisador_responde_como_pagina_inexistente(client, estudo):
    outro = Usuario.objects.create_user(
        "outro@alunos.umc.br", "Outro Pesquisador", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
    )
    client.force_login(outro)

    for rota in ("detalhe", "editar", "criterios"):
        assert client.get(endereco(rota, estudo)).status_code == 404


def test_RF05_CA01_busca_sem_acento_acha_a_variavel_com_acento(cliente, estudo):
    escolaridade = variavel("escolaridade")
    assert escolaridade.nome == "Escolaridade concluída"

    resposta = cliente.get(endereco("buscar_variaveis", estudo), {"q": "escolaridade concluida"})

    assert f'data-variavel="{escolaridade.id}"' in resposta.content.decode()


def test_RF05_CA02_busca_sem_resultado_oferece_propor_a_variavel_com_o_termo_digitado(cliente, estudo):
    resposta = cliente.get(endereco("buscar_variaveis", estudo), {"q": "xyzzyx"})
    pagina = resposta.content.decode()

    assert "Propor variável nova" in pagina
    assert endereco("propor_variavel", estudo) + "?nome=xyzzyx" in pagina


def test_RF05_filtra_os_resultados_por_subcategoria(cliente, estudo):
    escolaridade = variavel("escolaridade")
    outra = variavel("idade_anos")
    assert escolaridade.subcategoria_id != outra.subcategoria_id

    todas = cliente.get(endereco("buscar_variaveis", estudo), {"q": "e"}).content.decode()
    filtrada = cliente.get(
        endereco("buscar_variaveis", estudo), {"q": "e", "sub": escolaridade.subcategoria_id}
    ).content.decode()

    marca = 'data-variavel="{}"'
    assert marca.format(escolaridade.id) in todas and marca.format(escolaridade.id) in filtrada
    assert marca.format(outra.id) in todas and marca.format(outra.id) not in filtrada


def test_RF06_CA01_valor_acima_da_faixa_plausivel_e_recusado_indicando_o_maximo(cliente, estudo):
    idade = variavel("idade_anos")
    assert (idade.minimo, idade.maximo) == (0, 120)

    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, idade.id),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "150"},
    )

    assert resposta.status_code == 422
    assert "máximo plausível" in resposta.content.decode() and "120" in resposta.content.decode()
    assert not Criterio.objects.exists()


def test_RF06_RN16_segundo_valor_do_entre_precisa_ser_maior_que_o_primeiro(cliente, estudo):
    resposta = cliente.post(
        endereco("adicionar_criterio", estudo, variavel("idade_anos").id),
        {"tipo_regra": "inclusao", "operador": "entre", "valor_numero": "40", "valor_numero_ate": "30"},
    )

    assert resposta.status_code == 422
    assert not Criterio.objects.exists()


def test_RF07_CA01_criterio_removido_deixa_de_constar_no_estudo(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)
    assert estudo.situacao == Estudo.Situacao.RASCUNHO

    resposta = cliente.post(endereco("remover_criterio", estudo, criterio.id))

    assert resposta.status_code == 200
    assert not Criterio.objects.filter(pk=criterio.pk).exists()
    assert criterio.descricao not in resposta.content.decode()


def test_RF07_CA02_alteracao_para_fora_da_faixa_e_recusada_e_o_criterio_se_mantem(cliente, estudo):
    criterio = gravar(estudo, "idade_anos", "maior_igual", valor_numero=18)

    resposta = cliente.post(
        endereco("editar_criterio", estudo, criterio.id),
        {"tipo_regra": "inclusao", "operador": "maior_igual", "valor_numero": "150"},
    )

    criterio.refresh_from_db()
    assert resposta.status_code == 422
    assert criterio.valor_numero == 18
