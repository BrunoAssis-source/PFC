import pytest
from django.contrib import admin
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from autenticacao.models import Usuario
from voluntarios.conftest import criterio, novo_estudo, pesquisadora, profissional, variavel  # noqa: F401

Acao = RegistroAuditoria.Acao
SENHA = "Senha!2026x"


@pytest.fixture
def administrador(db):
    usuario = Usuario.objects.create_user(
        "admin@alunos.umc.br", "Administrador Teste", SENHA, perfil=Usuario.Perfil.PESQUISADOR
    )
    usuario.is_staff = True
    usuario.save()
    return usuario


def test_RF14_CA01_login_com_senha_incorreta_gera_registro_com_o_email_e_o_ip(client, db):
    Usuario.objects.create_user("ativo@alunos.umc.br", "Pessoa Ativa", SENHA, perfil=Usuario.Perfil.PESQUISADOR)

    client.post(reverse("login"), {"username": "ativo@alunos.umc.br", "password": "outra"}, REMOTE_ADDR="203.0.113.7")

    registro = RegistroAuditoria.objects.get(acao=Acao.LOGIN_FALHA)
    assert registro.email_tentativa == "ativo@alunos.umc.br"
    assert registro.ip == "203.0.113.7"


def test_RF14_CA02_quem_nao_e_administrador_recebe_403_e_a_tentativa_fica_registrada(
    client, pesquisadora, profissional
):
    for usuario in (pesquisadora, profissional):
        client.force_login(usuario)

        resposta = client.get(reverse("auditoria:listar"))

        assert resposta.status_code == 403
        registro = RegistroAuditoria.objects.get(acao=Acao.ACESSO_NEGADO, usuario=usuario)
        assert registro.objeto == reverse("auditoria:listar")


def test_RF14_visitante_e_mandado_ao_login(client, db):
    resposta = client.get(reverse("auditoria:listar"))

    assert resposta.status_code == 302
    assert not RegistroAuditoria.objects.filter(acao=Acao.ACESSO_NEGADO).exists()


def test_RF14_RN35_admin_do_django_nao_cria_altera_nem_exclui_registro(client, administrador):
    client.force_login(administrador)
    requisicao = client.get(reverse("auditoria:listar")).wsgi_request
    modelo = admin.site._registry[RegistroAuditoria]

    assert not modelo.has_add_permission(requisicao)
    assert not modelo.has_change_permission(requisicao)
    assert not modelo.has_delete_permission(requisicao)


def test_RF14_lista_pagina_de_50_em_50_do_mais_recente_para_o_mais_antigo(client, administrador):
    for numero in range(60):
        RegistroAuditoria.objects.create(acao=Acao.LOGOUT, objeto=f"registro-{numero}")
    client.force_login(administrador)

    pagina = client.get(reverse("auditoria:listar")).context["pagina"]

    assert len(pagina) == 50 and pagina.paginator.num_pages == 2
    assert pagina[0].criado_em >= pagina[-1].criado_em


@pytest.fixture
def estudo_sensivel(pesquisadora):
    estudo = novo_estudo(pesquisadora, "Estudo sensível")
    assert variavel("pessoa_com_deficiencia").sensivel
    criterio(estudo, "pessoa_com_deficiencia", "verdadeiro")
    return estudo


def test_RN34_exportar_estudo_com_variavel_sensivel_registra_o_acesso(client, pesquisadora, estudo_sensivel):
    client.force_login(pesquisadora)

    resposta = client.get(reverse("voluntarios:exportar", args=[estudo_sensivel.id]))

    assert resposta.status_code == 200
    registro = RegistroAuditoria.objects.get(acao=Acao.EXPORTACAO_SENSIVEL)
    assert registro.usuario == pesquisadora
    assert registro.objeto == estudo_sensivel.nome


def test_RN34_exportar_estudo_sem_variavel_sensivel_nao_gera_o_registro_especifico(client, pesquisadora):
    estudo = novo_estudo(pesquisadora, "Estudo comum")
    criterio(estudo, "numero_filhos", "maior_igual", valor_numero=1)
    client.force_login(pesquisadora)

    client.get(reverse("voluntarios:exportar", args=[estudo.id]))

    assert not RegistroAuditoria.objects.filter(acao=Acao.EXPORTACAO_SENSIVEL).exists()
    assert RegistroAuditoria.objects.filter(acao=Acao.ESTUDO_LEITURA).exists()


def test_RN34_exportacao_de_outro_pesquisador_e_404_e_nao_registra(client, estudo_sensivel):
    outro = Usuario.objects.create_user("outro@alunos.umc.br", "Outro", SENHA, perfil=Usuario.Perfil.PESQUISADOR)
    client.force_login(outro)

    resposta = client.get(reverse("voluntarios:exportar", args=[estudo_sensivel.id]))

    assert resposta.status_code == 404
    assert not RegistroAuditoria.objects.filter(acao=Acao.EXPORTACAO_SENSIVEL).exists()


def test_menu_marca_so_auditoria_na_tela_de_auditoria(client, administrador):
    import re

    client.force_login(administrador)

    html = client.get(reverse("auditoria:listar")).content.decode()

    ativos = re.findall(r'class="painel-item ativo"\s+href="([^"]+)"', html)
    assert ativos == [reverse("auditoria:listar")]


def test_menu_marca_estudos_na_lista_de_estudos(client, pesquisadora):
    import re

    client.force_login(pesquisadora)

    html = client.get(reverse("estudos:listar")).content.decode()

    ativos = re.findall(r'class="painel-item ativo"\s+href="([^"]+)"', html)
    assert ativos == [reverse("estudos:listar")]
