from datetime import timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from estudos.models import Estudo
from voluntarios import eliminacao
from voluntarios.models import Participacao, ValorColetado, Voluntario

from .conftest import criterio, novo_estudo
from .teste_decisoes import pessoa

Acao = RegistroAuditoria.Acao


@pytest.fixture
def cliente(client, pesquisadora):
    client.force_login(pesquisadora)
    return client


@pytest.fixture
def estudo(pesquisadora):
    novo = novo_estudo(pesquisadora, "Estudo com prazo")
    criterio(novo, "numero_filhos", "maior_igual", valor_numero=1)
    return novo


def com_prazo(estudo, dias):
    estudo.prazo_guarda_ate = timezone.localdate() + timedelta(days=dias)
    estudo.save()


def encerrar(cliente, estudo):
    return cliente.post(reverse("estudos:encerrar", args=[estudo.id]))


def existe(voluntario):
    return Voluntario.objects.filter(pk=voluntario.pk).exists()


def test_RN33_encerrar_antes_do_prazo_mantem_os_dados_e_registra_o_adiamento(cliente, profissional, estudo):
    com_prazo(estudo, 30)
    voluntario = pessoa(profissional, estudo, 1, filhos=2)

    resposta = encerrar(cliente, estudo)

    assert resposta.status_code == 302
    estudo.refresh_from_db()
    assert estudo.situacao == Estudo.Situacao.ENCERRADO
    assert existe(voluntario)
    assert ValorColetado.objects.filter(codigo_voluntario=voluntario.codigo_hmac).exists()
    registro = RegistroAuditoria.objects.get(acao=Acao.ELIMINACAO_ADIADA)
    assert estudo.prazo_guarda_ate.strftime("%d/%m/%Y") in registro.objeto
    assert not RegistroAuditoria.objects.filter(acao=Acao.ELIMINACAO_ENCERRAMENTO).exists()


def test_RN33_tela_de_confirmacao_avisa_que_a_eliminacao_espera_a_data(cliente, estudo):
    com_prazo(estudo, 30)

    html = cliente.get(reverse("estudos:encerrar", args=[estudo.id])).content.decode()

    assert estudo.prazo_guarda_ate.strftime("%d/%m/%Y") in html
    assert "Encerrar e guardar até a data" in html


def test_RN33_sem_prazo_a_eliminacao_continua_imediata(cliente, profissional, estudo):
    voluntario = pessoa(profissional, estudo, 1, filhos=2)

    encerrar(cliente, estudo)

    assert not existe(voluntario)
    assert not RegistroAuditoria.objects.filter(acao=Acao.ELIMINACAO_ADIADA).exists()


def test_RN33_prazo_ja_vencido_no_encerramento_elimina_na_hora(cliente, profissional, estudo):
    com_prazo(estudo, -1)
    voluntario = pessoa(profissional, estudo, 1, filhos=2)

    encerrar(cliente, estudo)

    assert not existe(voluntario)


def test_RN33_rotina_nao_elimina_antes_da_data(cliente, profissional, estudo):
    com_prazo(estudo, 30)
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    encerrar(cliente, estudo)

    call_command("eliminar_vencidos")

    assert existe(voluntario)


def test_RN33_rotina_elimina_quando_a_data_chega_e_audita_sem_dado_pessoal(cliente, profissional, estudo):
    com_prazo(estudo, 30)
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    encerrar(cliente, estudo)
    Estudo.objects.filter(pk=estudo.pk).update(prazo_guarda_ate=timezone.localdate())

    call_command("eliminar_vencidos")

    assert not existe(voluntario)
    registro = RegistroAuditoria.objects.get(acao=Acao.ELIMINACAO_ENCERRAMENTO)
    assert registro.usuario is None
    assert voluntario.codigo_hmac[:8] not in registro.objeto


def test_RN33_rotina_repetida_nao_duplica_o_registro_de_auditoria(cliente, profissional, estudo):
    com_prazo(estudo, 30)
    pessoa(profissional, estudo, 1, filhos=2)
    encerrar(cliente, estudo)
    Estudo.objects.filter(pk=estudo.pk).update(prazo_guarda_ate=timezone.localdate())

    call_command("eliminar_vencidos")
    call_command("eliminar_vencidos")

    assert RegistroAuditoria.objects.filter(acao=Acao.ELIMINACAO_ENCERRAMENTO).count() == 1


def test_RN33_estudo_encerrado_com_prazo_em_curso_segura_o_voluntario_de_outro_estudo(
    cliente, pesquisadora, profissional, estudo
):
    com_prazo(estudo, 30)
    outro = novo_estudo(pesquisadora, "Outro estudo")
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    Participacao.objects.create(
        voluntario=voluntario, estudo=outro, tcle_versao="1", registrado_por=profissional,
        situacao=Participacao.Situacao.CONCLUIDA,
    )
    encerrar(cliente, estudo)

    encerrar(cliente, outro)

    assert existe(voluntario)


def test_RN33_passado_o_prazo_o_voluntario_deixa_de_ser_seguro(pesquisadora, profissional, estudo):
    com_prazo(estudo, 30)
    outro = novo_estudo(pesquisadora, "Outro estudo")
    voluntario = pessoa(profissional, outro, 1, filhos=2)
    Participacao.objects.create(
        voluntario=voluntario, estudo=estudo, tcle_versao="1", registrado_por=profissional,
        situacao=Participacao.Situacao.CONCLUIDA,
    )
    Estudo.objects.filter(pk=estudo.pk).update(situacao=Estudo.Situacao.ENCERRADO)
    assert eliminacao.tem_outro_estudo_ativo(voluntario, outro)

    Estudo.objects.filter(pk=estudo.pk).update(prazo_guarda_ate=timezone.localdate())

    assert not eliminacao.tem_outro_estudo_ativo(voluntario, outro)


def test_RN33_prazo_nao_muda_depois_do_encerramento(cliente, estudo):
    com_prazo(estudo, 30)
    encerrar(cliente, estudo)
    estudo.refresh_from_db()
    original = estudo.prazo_guarda_ate

    cliente.post(
        reverse("estudos:editar", args=[estudo.id]),
        {
            "nome": estudo.nome,
            "condicao": estudo.condicao,
            "descricao": "",
            "situacao": "encerrado",
            "prazo_guarda_ate": (original + timedelta(days=90)).isoformat(),
        },
    )

    estudo.refresh_from_db()
    assert estudo.prazo_guarda_ate == original
