import pytest
from django.conf import settings
from django.urls import reverse

from autenticacao.models import Usuario
from voluntarios.models import ValorColetado

from .conftest import CPF_B, criterio, nova_participacao, novo_estudo


@pytest.fixture
def participacao(profissional, pesquisadora):
    estudo = novo_estudo(pesquisadora)
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    return nova_participacao(profissional, estudo)


def url(participacao):
    return reverse("voluntarios:coleta", args=[participacao.voluntario_id, participacao.id])


def test_anonimo_vai_para_o_login(client, participacao):
    for metodo in ("get", "post"):
        resposta = getattr(client, metodo)(url(participacao), {"variavel": 1, "valor": 2, "fonte": "voluntario"})
        assert resposta.status_code == 302 and resposta.url.startswith(f"{reverse(settings.LOGIN_URL)}?next=")


def test_pesquisador_recebe_negativa_e_nada_e_gravado(client, pesquisadora, participacao):
    client.force_login(pesquisadora)
    assert client.get(url(participacao)).status_code == 403
    assert client.post(url(participacao), {"variavel": 1, "valor": 2, "fonte": "voluntario"}).status_code == 403
    assert not ValorColetado.objects.exists()


def test_administrador_sem_perfil_de_profissional_recebe_negativa(client, participacao):
    admin = Usuario.objects.create_user(
        "adm@alunos.umc.br", "Administrador", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR, is_staff=True
    )
    client.force_login(admin)
    assert client.get(url(participacao)).status_code == 403


def test_profissional_acessa(cliente, participacao):
    assert cliente.get(url(participacao)).status_code == 200


def test_participacao_de_outro_voluntario_na_rota_da_ficha_errada_da_404(cliente, profissional, participacao):
    outra = nova_participacao(profissional, participacao.estudo, CPF_B)
    rota = reverse("voluntarios:coleta", args=[outra.voluntario_id, participacao.id])
    assert cliente.get(rota).status_code == 404
