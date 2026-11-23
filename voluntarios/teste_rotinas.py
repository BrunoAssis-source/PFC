from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from voluntarios.models import PendenciaNotificada, ValorColetado

from .conftest import criterio, novo_estudo
from .teste_decisoes import pessoa


@pytest.fixture
def estudo(pesquisadora):
    novo = novo_estudo(pesquisadora, "Estudo que exige filhos")
    criterio(novo, "numero_filhos", "maior_igual", valor_numero=1)
    return novo


def vencer(voluntario):
    ValorColetado.objects.filter(codigo_voluntario=voluntario.codigo_hmac, variavel__codigo="numero_filhos").update(
        coletado_em=timezone.now() - timedelta(days=400)
    )


def test_RN29_valor_que_vence_gera_o_aviso_so_quando_a_rotina_roda(profissional, pesquisadora, estudo):
    origem = novo_estudo(pesquisadora, "Estudo de origem")
    voluntario = pessoa(profissional, origem, 1, filhos=2)
    call_command("avisar_pendencias")
    assert mail.outbox == []

    vencer(voluntario)
    assert not PendenciaNotificada.objects.exists()

    call_command("avisar_pendencias")

    assert len(mail.outbox) == 1
    aviso = mail.outbox[0]
    assert aviso.to == [profissional.email]
    assert estudo.nome in aviso.subject
    assert voluntario.codigo_hmac[:8] in aviso.body
    assert PendenciaNotificada.objects.filter(voluntario=voluntario, estudo=estudo).exists()


def test_RN29_rotina_repetida_nao_avisa_duas_vezes_a_mesma_pendencia(profissional, pesquisadora, estudo):
    origem = novo_estudo(pesquisadora, "Estudo de origem")
    voluntario = pessoa(profissional, origem, 1, filhos=2)
    vencer(voluntario)

    call_command("avisar_pendencias")
    call_command("avisar_pendencias")

    assert len(mail.outbox) == 1
