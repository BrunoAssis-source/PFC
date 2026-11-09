import re

import pytest
from django.urls import reverse

from autenticacao.models import Usuario
from estudos.models import Criterio, Estudo
from estudos.painel import dados_do_painel
from voluntarios.models import Participacao

from .conftest import CPF_A, CPF_B, criterio, nova_participacao, novo_estudo

Situacao = Participacao.Situacao


def com_situacao(participacao, situacao, regra=None):
    participacao.situacao = situacao
    participacao.criterio_reprovado = regra
    participacao.save()
    return participacao


def cpf_de(indice):
    return f"{indice:011d}"


def nova(profissional, estudo, indice, situacao, regra=None):
    """Voluntário distinto por chamada. O CPF não precisa ser válido, só único, porque o teste cria direto no banco."""
    from voluntarios import cpf
    from voluntarios.models import Voluntario

    voluntario = Voluntario.objects.create(
        codigo_hmac=cpf.codigo(cpf_de(indice)), cpf_cifrado=cpf.cifrar(cpf_de(indice)), criado_por=profissional
    )
    return Participacao.objects.create(
        voluntario=voluntario, estudo=estudo, tcle_versao="1", registrado_por=profissional,
        situacao=situacao, criterio_reprovado=regra,
    )


@pytest.fixture
def cenario(profissional, pesquisadora):
    estudo = novo_estudo(pesquisadora, "Estudo A")
    estudo.participantes_necessarios = 4
    estudo.save()
    idade = criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    sexo = criterio(estudo, "cuidador_de_dependente", "verdadeiro")
    for i in range(1, 3):
        nova(profissional, estudo, i, Situacao.CONCLUIDA)
    nova(profissional, estudo, 3, Situacao.ELIMINADA, idade)
    nova(profissional, estudo, 4, Situacao.ELIMINADA, idade)
    nova(profissional, estudo, 5, Situacao.ELIMINADA, sexo)
    nova(profissional, estudo, 6, Situacao.EM_COLETA)
    return estudo, idade, sexo


def test_contagens_de_estudos_e_de_voluntarios(pesquisadora, cenario):
    outro = novo_estudo(pesquisadora, "Estudo B")
    outro.situacao = Estudo.Situacao.ENCERRADO
    outro.save()
    Estudo.objects.create(nome="Rascunho", condicao="c", pesquisador=pesquisadora)

    dados = dados_do_painel(pesquisadora)

    assert dict(dados["por_situacao"]) == {"Rascunho": 1, "Ativo": 1, "Encerrado": 1}
    assert dados["concluidos"] == 2
    assert dados["eliminados"] == 3


def test_progresso_e_triagem_por_estudo(pesquisadora, cenario):
    linha = next(l for l in dados_do_painel(pesquisadora)["estudos"] if l["estudo"].nome == "Estudo A")

    assert (linha["concluidos"], linha["eliminados"], linha["em_coleta"], linha["triados"]) == (2, 3, 1, 6)
    assert linha["meta"] == 4 and linha["progresso"] == 50
    assert [f["largura"] for f in linha["faixas"]] == [33, 50, 17]


def test_progresso_nao_passa_de_100_e_sem_meta_fica_vazio(pesquisadora, profissional, cenario):
    estudo, *_ = cenario
    estudo.participantes_necessarios = 1
    estudo.save()
    sem_meta = novo_estudo(pesquisadora, "Sem meta")
    nova(profissional, sem_meta, 20, Situacao.CONCLUIDA)

    linhas = {l["estudo"].nome: l for l in dados_do_painel(pesquisadora)["estudos"]}

    assert linhas["Estudo A"]["progresso"] == 100
    assert linhas["Sem meta"]["progresso"] is None


def test_eliminacoes_por_criterio_usam_o_criterio_registrado_na_participacao(pesquisadora, cenario):
    estudo, idade, sexo = cenario

    linha = next(l for l in dados_do_painel(pesquisadora)["estudos"] if l["estudo"] == estudo)

    assert linha["criterios"] == [
        {"frase": idade.frase, "total": 2},
        {"frase": sexo.frase, "total": 1},
    ]


def test_criterio_removido_aparece_como_removido(pesquisadora, profissional):
    estudo = novo_estudo(pesquisadora)
    regra = criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    nova(profissional, estudo, 1, Situacao.ELIMINADA, regra)
    regra.delete()

    linha = dados_do_painel(pesquisadora)["estudos"][0]

    assert linha["criterios"] == [{"frase": "Critério removido do estudo", "total": 1}]


def test_so_entram_os_estudos_do_proprio_pesquisador(pesquisadora, profissional, cenario):
    outra = Usuario.objects.create_user("outra@alunos.umc.br", "Outra", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR)
    alheio = novo_estudo(outra, "Estudo alheio")
    nova(profissional, alheio, 30, Situacao.CONCLUIDA)
    nova(profissional, alheio, 31, Situacao.ELIMINADA)

    dados = dados_do_painel(pesquisadora)

    assert {l["estudo"].nome for l in dados["estudos"]} == {"Estudo A"}
    assert (dados["concluidos"], dados["eliminados"]) == (2, 3)
    assert dados_do_painel(outra)["eliminados"] == 1


def test_coletas_por_semana_contam_as_participacoes_recentes(pesquisadora, cenario):
    semanas = dados_do_painel(pesquisadora)["semanas"]

    assert len(semanas) == 8
    assert semanas[-1]["total"] == 6 and sum(s["total"] for s in semanas) == 6
    assert semanas[-1]["altura"] == 100 and semanas[0]["altura"] == 0


def test_coleta_antiga_fica_fora_das_oito_semanas(pesquisadora, profissional):
    from datetime import timedelta

    from django.utils import timezone

    estudo = novo_estudo(pesquisadora)
    antiga = nova(profissional, estudo, 40, Situacao.CONCLUIDA)
    Participacao.objects.filter(pk=antiga.pk).update(tcle_aceito_em=timezone.now() - timedelta(weeks=12))

    semanas = dados_do_painel(pesquisadora)["semanas"]

    assert sum(s["total"] for s in semanas) == 0


def test_tela_inicial_do_pesquisador_mostra_o_painel_sem_cpf_nem_codigo(client, pesquisadora, cenario):
    client.force_login(pesquisadora)

    pagina = client.get(reverse("inicio")).content.decode()

    assert "Progresso por estudo" in pagina and "2 de 4 participantes" in pagina
    assert "Eliminações por critério" in pagina and "Coletas iniciadas por semana" in pagina
    assert not re.search(r"\b[0-9a-f]{8,64}\b", pagina.replace("csrfmiddlewaretoken", ""))
    for numero in (CPF_A, CPF_B, cpf_de(1)):
        assert numero not in pagina


def test_estado_vazio_sem_estudos(client, pesquisadora):
    client.force_login(pesquisadora)

    pagina = client.get(reverse("inicio")).content.decode()

    assert "Você ainda não tem estudos" in pagina
    assert "Progresso por estudo" not in pagina


def test_estado_vazio_com_estudo_e_sem_coletas(client, pesquisadora):
    novo_estudo(pesquisadora)
    client.force_login(pesquisadora)

    pagina = client.get(reverse("inicio")).content.decode()

    assert "Nenhuma coleta foi iniciada" in pagina
    assert "Progresso por estudo" not in pagina


def test_profissional_nao_ve_o_painel_nem_os_numeros(client, profissional, cenario):
    client.force_login(profissional)

    resposta = client.get(reverse("inicio"))
    pagina = resposta.content.decode()

    assert resposta.status_code == 200
    assert "painel" not in resposta.context
    for trecho in ("Progresso por estudo", "Voluntários eliminados", "Eliminações por critério", "Estudo A"):
        assert trecho not in pagina


def test_anonimo_vai_para_o_login(client):
    resposta = client.get(reverse("inicio"))

    assert resposta.status_code == 302 and resposta.url.startswith(reverse("login"))
