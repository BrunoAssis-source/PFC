from django.urls import reverse

from auditoria.models import RegistroAuditoria
from estudos.models import Estudo
from voluntarios import cpf
from voluntarios.models import Participacao, Voluntario

from .conftest import CPF_A, CPF_B

Acao = RegistroAuditoria.Acao


def cadastrar(cliente, numero=CPF_A):
    return cliente.post(reverse("voluntarios:cadastrar"), {"cpf": numero})


def acoes():
    return list(RegistroAuditoria.objects.values_list("acao", flat=True))


def test_busca_de_cpf_inexistente_oferece_cadastro_e_mostra_so_a_mascara(cliente):
    resposta = cliente.post(reverse("voluntarios:identificar"), {"cpf": "529.982.247-25"})
    conteudo = resposta.content.decode()
    assert "Cadastrar novo voluntário" in conteudo
    assert "***.982.247-**" in conteudo
    assert Acao.VOLUNTARIO_BUSCA in acoes()


def test_busca_de_cpf_existente_abre_o_voluntario(cliente, profissional):
    cadastrar(cliente)
    voluntario = Voluntario.objects.get()
    resposta = cliente.post(reverse("voluntarios:identificar"), {"cpf": CPF_A})
    assert resposta.url == reverse("voluntarios:detalhe", args=[voluntario.id])


def test_cpf_invalido_nao_cadastra(cliente):
    cadastrar(cliente, "52998224726")
    assert not Voluntario.objects.exists()


def test_cadastro_grava_cifrado_e_com_codigo(cliente, profissional):
    cadastrar(cliente)
    voluntario = Voluntario.objects.get()
    assert voluntario.codigo_hmac == cpf.codigo(CPF_A)
    assert CPF_A not in voluntario.cpf_cifrado
    assert cpf.decifrar(voluntario.cpf_cifrado) == CPF_A
    assert voluntario.criado_por == profissional


def test_cpf_com_pontuacao_e_sem_pontuacao_sao_o_mesmo_voluntario(cliente):
    cadastrar(cliente, "529.982.247-25")
    cadastrar(cliente, CPF_A)
    assert Voluntario.objects.count() == 1


def test_segundo_cadastro_do_mesmo_cpf_nao_duplica_e_e_auditado(cliente):
    cadastrar(cliente)
    resposta = cadastrar(cliente)
    assert Voluntario.objects.count() == 1
    assert resposta.url == reverse("voluntarios:detalhe", args=[Voluntario.objects.get().id])


def test_cadastro_concorrente_cai_no_voluntario_existente(cliente, profissional, monkeypatch):
    # Simula o outro profissional que gravou o CPF entre a busca e o envio.
    Voluntario.objects.create(codigo_hmac=cpf.codigo(CPF_A), cpf_cifrado=cpf.cifrar(CPF_A), criado_por=profissional)
    cadastrar(cliente)
    assert Voluntario.objects.count() == 1
    assert Acao.VOLUNTARIO_DUPLICADO in acoes()


def test_tela_do_voluntario_mostra_cpf_mascarado(cliente):
    cadastrar(cliente)
    voluntario = Voluntario.objects.get()
    conteudo = cliente.get(reverse("voluntarios:detalhe", args=[voluntario.id])).content.decode()
    assert "***.982.247-**" in conteudo and CPF_A not in conteudo
    assert Acao.VOLUNTARIO_LEITURA in acoes()


def test_auditoria_nunca_guarda_o_cpf(cliente):
    cadastrar(cliente)
    cliente.post(reverse("voluntarios:identificar"), {"cpf": CPF_A})
    for registro in RegistroAuditoria.objects.all():
        assert CPF_A not in registro.objeto


def vincular(cliente, voluntario, estudo, tcle=True):
    dados = {"estudo": estudo.id}
    if tcle:
        dados["tcle"] = "on"
    return cliente.post(reverse("voluntarios:vincular", args=[voluntario.id]), dados)


def test_vinculo_exige_o_tcle(cliente, estudo_ativo):
    cadastrar(cliente)
    vincular(cliente, Voluntario.objects.get(), estudo_ativo, tcle=False)
    assert not Participacao.objects.exists()


def test_vinculo_registra_tcle_e_auditoria(cliente, profissional, estudo_ativo):
    cadastrar(cliente)
    vincular(cliente, Voluntario.objects.get(), estudo_ativo)
    participacao = Participacao.objects.get()
    assert participacao.tcle_versao and participacao.tcle_aceito_em
    assert participacao.registrado_por == profissional
    assert participacao.situacao == Participacao.Situacao.EM_COLETA
    assert Acao.PARTICIPACAO_VINCULO in acoes()


def test_mesmo_voluntario_nao_entra_duas_vezes_no_estudo(cliente, estudo_ativo):
    cadastrar(cliente)
    voluntario = Voluntario.objects.get()
    vincular(cliente, voluntario, estudo_ativo)
    vincular(cliente, voluntario, estudo_ativo)
    assert Participacao.objects.count() == 1


def test_estudo_em_rascunho_ou_encerrado_nao_recebe_voluntario(cliente, estudo_ativo):
    cadastrar(cliente)
    voluntario = Voluntario.objects.get()
    for situacao in (Estudo.Situacao.RASCUNHO, Estudo.Situacao.ENCERRADO):
        estudo_ativo.situacao = situacao
        estudo_ativo.save()
        vincular(cliente, voluntario, estudo_ativo)
    assert not Participacao.objects.exists()


def test_voluntarios_diferentes_tem_codigos_diferentes(cliente):
    cadastrar(cliente, CPF_A)
    cadastrar(cliente, CPF_B)
    assert Voluntario.objects.values("codigo_hmac").distinct().count() == 2
