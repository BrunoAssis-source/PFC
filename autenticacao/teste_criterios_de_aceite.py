from datetime import datetime, timedelta

import pytest
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from auditoria.models import RegistroAuditoria
from autenticacao.models import Usuario

pytestmark = pytest.mark.django_db

SENHA = "Senha!2026x"
Acao = RegistroAuditoria.Acao


def dados_de_cadastro(**mudancas):
    dados = {
        "nome_completo": "Pessoa Teste",
        "email": "pessoa@alunos.umc.br",
        "perfil": Usuario.Perfil.PESQUISADOR,
        "password1": "Frase longa 2026 azul",
        "password2": "Frase longa 2026 azul",
        "aceite": "on",
    }
    dados.update(mudancas)
    return dados


def criar(email="ativo@alunos.umc.br", perfil=Usuario.Perfil.PESQUISADOR, **campos):
    return Usuario.objects.create_user(email, "Usuário Ativo", SENHA, perfil=perfil, **campos)


def test_RF01_CA01_email_fora_do_dominio_e_recusado_com_o_dominio_exigido(client):
    resposta = client.post(reverse("cadastro"), dados_de_cadastro(email="pessoa@gmail.com"))

    assert resposta.status_code == 200
    assert "@alunos.umc.br" in resposta.content.decode()
    assert not Usuario.objects.exists()


def test_RF01_CA02_email_ja_cadastrado_e_recusado(client):
    criar("pessoa@alunos.umc.br")

    resposta = client.post(reverse("cadastro"), dados_de_cadastro())

    assert resposta.status_code == 200
    assert Usuario.objects.count() == 1


def test_RF01_CA02_email_repetido_com_outra_caixa_tambem_e_recusado(client):
    criar("pessoa@alunos.umc.br")

    client.post(reverse("cadastro"), dados_de_cadastro(email="PESSOA@alunos.umc.br"))

    assert Usuario.objects.count() == 1


def test_RF01_CA03_dados_validos_e_termos_aceitos_criam_a_conta_com_o_perfil_escolhido(client):
    resposta = client.post(reverse("cadastro"), dados_de_cadastro(perfil=Usuario.Perfil.PROFISSIONAL))

    assert resposta.status_code == 302
    usuario = Usuario.objects.get()
    assert usuario.email == "pessoa@alunos.umc.br"
    assert usuario.perfil == Usuario.Perfil.PROFISSIONAL
    assert RegistroAuditoria.objects.filter(acao=Acao.CADASTRO, usuario=usuario).exists()


@pytest.mark.xfail(
    strict=True,
    reason="Divergência do RF01: o código exige confirmar o email antes de ativar a conta e não inicia a sessão.",
)
def test_RF01_CA03_usuario_e_direcionado_a_tela_inicial(client):
    resposta = client.post(reverse("cadastro"), dados_de_cadastro())

    assert resposta.status_code == 302 and resposta.url == reverse("inicio")


def test_RF01_RN02_cadastro_sem_aceitar_os_termos_e_recusado(client):
    dados = dados_de_cadastro()
    del dados["aceite"]

    resposta = client.post(reverse("cadastro"), dados)

    assert resposta.status_code == 200
    assert "Aceite os termos" in resposta.content.decode()
    assert not Usuario.objects.exists()


def test_RF01_RN03_administrador_corrige_o_perfil_e_desativa_a_conta(client):
    administrador = criar("adm@alunos.umc.br", is_staff=True)
    alvo = criar("alvo@alunos.umc.br", perfil=Usuario.Perfil.PROFISSIONAL)
    client.force_login(administrador)

    client.post(
        reverse("editar_usuario", args=[alvo.id]),
        {"nome_completo": alvo.nome_completo, "email": alvo.email, "perfil": Usuario.Perfil.PESQUISADOR},
    )

    alvo.refresh_from_db()
    assert alvo.perfil == Usuario.Perfil.PESQUISADOR
    assert not alvo.is_active


def test_RF02_CA01_credenciais_corretas_levam_a_tela_inicial(client):
    criar()

    resposta = client.post(reverse("login"), {"username": "ativo@alunos.umc.br", "password": SENHA})

    assert resposta.status_code == 302 and resposta.url == reverse("inicio")
    assert RegistroAuditoria.objects.filter(acao=Acao.LOGIN_SUCESSO).exists()


def test_RF02_CA02_senha_incorreta_e_recusada_com_mensagem_generica_e_auditada(client):
    criar()

    errada = client.post(reverse("login"), {"username": "ativo@alunos.umc.br", "password": "outra"})
    inexistente = client.post(reverse("login"), {"username": "ninguem@alunos.umc.br", "password": "outra"})

    assert errada.status_code == 200
    mensagens = {resposta.context["form"].non_field_errors()[0] for resposta in (errada, inexistente)}
    assert len(mensagens) == 1
    falha = RegistroAuditoria.objects.filter(acao=Acao.LOGIN_FALHA, email_tentativa="ativo@alunos.umc.br").get()
    assert falha.ip


def test_RF02_CA02_conta_desativada_e_recusada_com_a_mesma_mensagem_e_auditada(client):
    from django.utils import timezone

    criar("inativo@alunos.umc.br", is_active=False, last_login=timezone.now())
    criar()

    desativada = client.post(reverse("login"), {"username": "inativo@alunos.umc.br", "password": SENHA})
    errada = client.post(reverse("login"), {"username": "ativo@alunos.umc.br", "password": "outra"})

    assert desativada.status_code == 200
    assert desativada.context["form"].non_field_errors() == errada.context["form"].non_field_errors()
    assert "_auth_user_id" not in client.session
    assert RegistroAuditoria.objects.filter(acao=Acao.LOGIN_FALHA, email_tentativa="inativo@alunos.umc.br").exists()


def test_RF02_CA03_profissional_nao_acessa_a_lista_de_estudos_e_a_tentativa_e_registrada(client):
    profissional = criar("prof@alunos.umc.br", perfil=Usuario.Perfil.PROFISSIONAL)
    client.force_login(profissional)

    resposta = client.get(reverse("estudos:listar"))

    assert resposta.status_code == 403
    registro = RegistroAuditoria.objects.get(acao=Acao.ACESSO_NEGADO, usuario=profissional)
    assert registro.objeto == reverse("estudos:listar")


def test_RF02_logout_encerra_a_sessao_e_registra(client):
    usuario = criar()
    client.force_login(usuario)

    client.post(reverse("logout"))

    assert "_auth_user_id" not in client.session
    assert RegistroAuditoria.objects.filter(acao=Acao.LOGOUT, usuario=usuario).exists()


def test_RF03_CA01_email_sem_cadastro_recebe_a_mesma_confirmacao_de_um_cadastrado(client):
    criar("cadastrado@alunos.umc.br")

    com_conta = client.post(reverse("senha_reset"), {"email": "cadastrado@alunos.umc.br"})
    enviados = len(mail.outbox)
    sem_conta = client.post(reverse("senha_reset"), {"email": "semconta@alunos.umc.br"})

    assert (com_conta.status_code, com_conta.url) == (sem_conta.status_code, sem_conta.url)
    assert enviados == 1 and len(mail.outbox) == 1
    assert client.get(sem_conta.url).content == client.get(com_conta.url).content


def endereco_de_redefinicao(usuario):
    token = default_token_generator.make_token(usuario)
    return reverse("senha_reset_confirm", args=[urlsafe_base64_encode(force_bytes(usuario.pk)), token])


def test_RF03_CA02_link_ja_utilizado_e_recusado(client):
    usuario = criar()
    endereco = endereco_de_redefinicao(usuario)

    abrir = client.get(endereco, follow=True)
    assert abrir.context["validlink"]
    enviar = client.post(abrir.redirect_chain[-1][0], {"new_password1": "Outra frase 2026 verde", "new_password2": "Outra frase 2026 verde"})
    assert enviar.status_code == 302

    segunda = client.get(endereco)
    assert segunda.status_code == 200 and not segunda.context["validlink"]
    usuario.refresh_from_db()
    assert usuario.check_password("Outra frase 2026 verde")
    assert RegistroAuditoria.objects.filter(acao=Acao.SENHA_REDEFINIDA, usuario=usuario).exists()


def test_RF03_CA02_link_emitido_ha_mais_de_3_dias_e_recusado(client, monkeypatch):
    usuario = criar()
    endereco = endereco_de_redefinicao(usuario)

    monkeypatch.setattr(PasswordResetTokenGenerator, "_now", lambda self: datetime.now() + timedelta(days=4))
    resposta = client.get(endereco)

    assert resposta.status_code == 200 and not resposta.context["validlink"]


def test_RF03_RN07_link_com_menos_de_3_dias_ainda_vale(client, monkeypatch):
    usuario = criar()
    endereco = endereco_de_redefinicao(usuario)

    monkeypatch.setattr(PasswordResetTokenGenerator, "_now", lambda self: datetime.now() + timedelta(days=2))

    assert client.get(endereco, follow=True).context["validlink"]
