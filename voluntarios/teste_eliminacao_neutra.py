import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from estudos.models import Criterio
from voluntarios.coleta import proxima_variavel

from .conftest import criterio, nova_participacao, novo_estudo, opcoes

MENSAGEM = "Coleta encerrada: este voluntário não é compatível com o estudo."
EXCLUSAO = Criterio.TipoRegra.EXCLUSAO

# Cada caso elimina o voluntário por um tipo de critério e de variável diferente.
CASOS = {
    "nominal comum": lambda e: criterio(e, "sexo_ao_nascer", "e", opcoes("sexo_ao_nascer", "feminino")),
    "nominal sensivel": lambda e: criterio(e, "raca_cor", "e", opcoes("raca_cor", "branca")),
    "booleana sensivel": lambda e: criterio(e, "pessoa_com_deficiencia", "falso", tipo_regra=EXCLUSAO),
    "numerica": lambda e: criterio(e, "numero_filhos", "maior_igual", valor_numero=5),
}
RESPOSTAS = {
    "nominal comum": lambda: opcoes("sexo_ao_nascer", "masculino")[0].id,
    "nominal sensivel": lambda: opcoes("raca_cor", "preta")[0].id,
    "booleana sensivel": lambda: "nao",
    "numerica": lambda: 1,
}
# Para a booleana sensível o critério é de exclusão de "falso", então a resposta que elimina é "não".


def eliminar(cliente, pesquisadora, profissional, caso):
    estudo = novo_estudo(pesquisadora, f"Estudo {caso}")
    CASOS[caso](estudo)
    participacao = nova_participacao(profissional, estudo)
    variavel = proxima_variavel(participacao, {})
    url = reverse("voluntarios:coleta", args=[participacao.voluntario_id, participacao.id])
    with CaptureQueriesContext(connection) as consultas:
        resposta = cliente.post(
            url, {"variavel": variavel.id, "valor": RESPOSTAS[caso](), "fonte": "voluntario"}
        )
    final = cliente.get(url)
    participacao.refresh_from_db()
    return participacao, resposta, final, len(consultas), variavel


def sem_token(conteudo):
    # Token do formulário de saída e ids da rota mudam a cada execução e não dizem nada sobre a eliminação.
    conteudo = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", conteudo)
    return re.sub(r"/voluntarios/\d+/(participacoes/\d+/)?", "/voluntarios/N/", conteudo)


@pytest.fixture
def eliminados(cliente, pesquisadora, profissional):
    return {caso: eliminar(cliente, pesquisadora, profissional, caso) for caso in CASOS}


def test_todos_os_casos_realmente_eliminam(eliminados):
    for caso, (participacao, *_resto) in eliminados.items():
        assert participacao.situacao == "eliminada", caso
        assert participacao.criterio_reprovado is not None, caso


def test_mensagem_e_exatamente_a_combinada(eliminados):
    for caso, (_p, _resposta, final, _n, _v) in eliminados.items():
        assert MENSAGEM in final.content.decode(), caso


def test_resposta_e_tela_sao_identicas_em_qualquer_caso(eliminados):
    respostas = {caso: (r.status_code, r.url) for caso, (_p, r, _f, _n, _v) in eliminados.items()}
    # A rota de destino traz o id da participação, então compara o que vem depois dele.
    destinos = {(status, re.sub(r"/\d+/", "/N/", url)) for status, url in respostas.values()}
    assert len(destinos) == 1
    telas = {sem_token(f.content.decode()) for _p, _r, f, _n, _v in eliminados.values()}
    assert len(telas) == 1


def test_comum_e_sensivel_fazem_o_mesmo_numero_de_consultas(eliminados):
    # O número de consultas é o que se compara no lugar do tempo, que oscila entre execuções.
    assert eliminados["nominal comum"][3] == eliminados["nominal sensivel"][3]
    assert eliminados["booleana sensivel"][3] == eliminados["nominal sensivel"][3]


def test_tela_nao_expoe_criterio_variavel_nem_valor(eliminados):
    for caso, (participacao, _r, final, _n, variavel) in eliminados.items():
        pagina = final.content.decode().lower()
        regra = participacao.criterio_reprovado
        for proibido in (variavel.nome, variavel.codigo, regra.frase, "critério", "inclusão", "exclusão"):
            assert proibido.lower() not in pagina, (caso, proibido)
        assert "sensível" not in pagina and "sensivel" not in pagina, caso


def test_a_ficha_tambem_nao_distingue_os_casos(cliente, eliminados):
    fichas = set()
    for participacao, *_ in eliminados.values():
        ficha = cliente.get(reverse("voluntarios:detalhe", args=[participacao.voluntario_id])).content.decode()
        assert "eliminada" not in ficha
        fichas.add("encerrada" in ficha)
    assert fichas == {True}
