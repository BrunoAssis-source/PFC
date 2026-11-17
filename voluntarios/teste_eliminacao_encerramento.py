import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from autenticacao.models import Usuario
from estudos.admin import EstudoAdmin
from estudos.models import Estudo
from estudos.painel import dados_do_painel
from voluntarios import cpf, decisoes, eliminacao
from voluntarios.models import (
    DecisaoCandidato,
    Participacao,
    RegistroAnonimo,
    ValorColetado,
    ValorSensivel,
    Voluntario,
)

from .conftest import criterio, novo_estudo, opcoes
from .teste_decisoes import cpf_sintetico, pessoa
from .teste_verificacao import valor

Situacao = Participacao.Situacao
Decisao = DecisaoCandidato.Decisao


@pytest.fixture
def cliente(client, pesquisadora):
    client.force_login(pesquisadora)
    return client


@pytest.fixture
def estudo(pesquisadora):
    novo = novo_estudo(pesquisadora, "Estudo a encerrar")
    criterio(novo, "numero_filhos", "maior_igual", valor_numero=1)
    return novo


@pytest.fixture
def outro_ativo(pesquisadora):
    return novo_estudo(pesquisadora, "Outro estudo ativo")


def encerrar(cliente, estudo):
    return cliente.post(reverse("estudos:encerrar", args=[estudo.id]))


def vinculo(profissional, voluntario, estudo, situacao=Situacao.CONCLUIDA):
    return Participacao.objects.create(
        voluntario=voluntario, estudo=estudo, tcle_versao="1", registrado_por=profissional, situacao=situacao
    )


def existe(voluntario):
    return Voluntario.objects.filter(pk=voluntario.pk).exists()


def valores_de(voluntario):
    codigo = voluntario.codigo_hmac
    return ValorColetado.objects.filter(codigo_voluntario=codigo).count() + ValorSensivel.objects.filter(
        codigo_voluntario=codigo
    ).count()


def test_RF13_CA01_voluntario_de_um_unico_estudo_tem_os_dados_eliminados_ao_encerrar(
    cliente, profissional, estudo
):
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    valor(
        Participacao.objects.get(voluntario=voluntario), "pessoa_com_deficiencia", profissional,
        modelo=ValorSensivel, valor_booleano=False,
    )
    codigo = voluntario.codigo_hmac
    assert valores_de(voluntario) == 3

    resposta = encerrar(cliente, estudo)

    estudo.refresh_from_db()
    assert resposta.status_code == 302 and estudo.situacao == Estudo.Situacao.ENCERRADO
    assert not Voluntario.objects.filter(codigo_hmac=codigo).exists()
    assert not ValorColetado.objects.filter(codigo_voluntario=codigo).exists()
    assert not ValorSensivel.objects.filter(codigo_voluntario=codigo).exists()
    assert not Participacao.objects.exists()


def test_RF13_CA02_voluntario_em_dois_estudos_ativos_mantem_os_dados_ao_encerrar_um(
    cliente, profissional, estudo, outro_ativo
):
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    vinculo(profissional, voluntario, outro_ativo)
    antes = valores_de(voluntario)

    encerrar(cliente, estudo)

    estudo.refresh_from_db()
    assert estudo.situacao == Estudo.Situacao.ENCERRADO
    assert existe(voluntario) and valores_de(voluntario) == antes
    assert Participacao.objects.filter(voluntario=voluntario).count() == 2
    assert not RegistroAnonimo.objects.exists()


def test_voluntario_so_com_recusa_e_sem_outro_estudo_ativo_e_eliminado(cliente, pesquisadora, profissional, estudo):
    encerrado_antes = novo_estudo(pesquisadora, "Estudo de origem")
    voluntario = pessoa(profissional, encerrado_antes, 1, filhos=2)
    encerrado_antes.situacao = Estudo.Situacao.ENCERRADO
    encerrado_antes.save()
    DecisaoCandidato.objects.create(
        estudo=estudo, codigo_voluntario=voluntario.codigo_hmac, decisao=Decisao.RECUSADO,
        decidido_por=pesquisadora, decidido_em=estudo.criado_em, classificacao_na_decisao="elegivel",
    )

    encerrar(cliente, estudo)

    assert not existe(voluntario)
    assert not DecisaoCandidato.objects.exists()


@pytest.mark.parametrize("decisao", [Decisao.RECUSADO, Decisao.INCLUIDO])
def test_decisao_em_outro_estudo_ativo_mantem_o_voluntario(
    cliente, pesquisadora, profissional, estudo, outro_ativo, decisao
):
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    DecisaoCandidato.objects.create(
        estudo=outro_ativo, codigo_voluntario=voluntario.codigo_hmac, decisao=decisao,
        decidido_por=pesquisadora, decidido_em=estudo.criado_em, classificacao_na_decisao="elegivel",
    )

    encerrar(cliente, estudo)

    assert existe(voluntario) and valores_de(voluntario) == 2


def test_vinculo_so_com_estudo_em_rascunho_nao_segura_os_dados(cliente, pesquisadora, profissional, estudo):
    rascunho = Estudo.objects.create(nome="Rascunho", condicao="c", pesquisador=pesquisadora)
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    vinculo(profissional, voluntario, rascunho)

    encerrar(cliente, estudo)

    assert not existe(voluntario)
    assert RegistroAnonimo.objects.filter(estudo=rascunho).count() == 1


def test_falha_no_meio_da_eliminacao_nao_apaga_nada_e_mantem_a_situacao(
    pesquisadora, profissional, estudo, monkeypatch
):
    primeiro = pessoa(profissional, estudo, 1, filhos=2)
    segundo = pessoa(profissional, estudo, 2, filhos=3)

    def falha(voluntarios):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(eliminacao, "apagar_dados", falha)

    with pytest.raises(RuntimeError):
        eliminacao.encerrar(estudo, pesquisadora)

    estudo.refresh_from_db()
    assert estudo.situacao == Estudo.Situacao.ATIVO
    assert existe(primeiro) and existe(segundo)
    assert valores_de(primeiro) == 2 and valores_de(segundo) == 2
    assert Participacao.objects.count() == 2
    assert not RegistroAnonimo.objects.exists()
    assert not RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.ELIMINACAO_ENCERRAMENTO).exists()


def test_estudo_encerrado_nao_volta_a_ativo_pelo_modelo(cliente, estudo):
    encerrar(cliente, estudo)
    estudo.refresh_from_db()

    estudo.situacao = Estudo.Situacao.ATIVO
    with pytest.raises(ValidationError, match="dados dos voluntários já foram eliminados"):
        estudo.save()

    estudo.refresh_from_db()
    assert estudo.situacao == Estudo.Situacao.ENCERRADO


def test_servidor_recusa_reabrir_pelo_formulario_com_a_mensagem(cliente, estudo):
    encerrar(cliente, estudo)
    dados = {"nome": estudo.nome, "condicao": estudo.condicao, "descricao": "", "situacao": "ativo"}

    resposta = cliente.post(reverse("estudos:editar", args=[estudo.id]), dados)

    estudo.refresh_from_db()
    assert resposta.status_code == 200
    assert "dados dos voluntários já foram eliminados" in resposta.content.decode()
    assert estudo.situacao == Estudo.Situacao.ENCERRADO


def test_tela_de_edicao_do_encerrado_so_oferece_a_situacao_encerrado(cliente, estudo):
    encerrar(cliente, estudo)

    pagina = cliente.get(reverse("estudos:editar", args=[estudo.id])).content.decode()

    assert 'value="ativo"' not in pagina and 'value="rascunho"' not in pagina
    assert "dados dos voluntários já foram eliminados" in pagina


def test_admin_nao_edita_a_situacao_de_estudo_existente(estudo):
    modelo_admin = EstudoAdmin(Estudo, admin.site)

    assert "situacao" in modelo_admin.get_readonly_fields(None, estudo)
    assert "situacao" not in modelo_admin.get_readonly_fields(None, None)


def test_encerrar_de_novo_e_recusado(cliente, estudo):
    encerrar(cliente, estudo)

    assert cliente.get(reverse("estudos:encerrar", args=[estudo.id])).status_code == 403
    assert encerrar(cliente, estudo).status_code == 403
    assert RegistroAuditoria.objects.filter(acao=RegistroAuditoria.Acao.ELIMINACAO_ENCERRAMENTO).count() == 1


def test_escolher_encerrado_no_formulario_leva_a_confirmacao_sem_encerrar(cliente, profissional, estudo):
    voluntario = pessoa(profissional, estudo, 1, filhos=2)
    dados = {"nome": estudo.nome, "condicao": estudo.condicao, "descricao": "", "situacao": "encerrado"}

    resposta = cliente.post(reverse("estudos:editar", args=[estudo.id]), dados)

    estudo.refresh_from_db()
    assert resposta.status_code == 302 and resposta.url == reverse("estudos:encerrar", args=[estudo.id])
    assert estudo.situacao == Estudo.Situacao.ATIVO and existe(voluntario)


def test_confirmacao_mostra_so_as_quantidades(cliente, profissional, estudo, outro_ativo):
    sozinho = pessoa(profissional, estudo, 1, filhos=2)
    compartilhado = pessoa(profissional, estudo, 2, filhos=2)
    vinculo(profissional, compartilhado, outro_ativo)

    resposta = cliente.get(reverse("estudos:encerrar", args=[estudo.id]))

    texto = resposta.content.decode()
    assert resposta.context["eliminados"] == 1 and resposta.context["mantidos"] == 1
    assert "Esta ação não pode ser desfeita" in texto
    assert sozinho.codigo_hmac[:8] not in texto and cpf_sintetico(1) not in texto
    estudo.refresh_from_db()
    assert estudo.situacao == Estudo.Situacao.ATIVO and existe(sozinho)


def test_auditoria_registra_o_encerramento_sem_dados_pessoais(cliente, pesquisadora, profissional, estudo, outro_ativo):
    eliminado = pessoa(profissional, estudo, 1, filhos=2)
    mantido = pessoa(profissional, estudo, 2, filhos=2)
    vinculo(profissional, mantido, outro_ativo)
    codigos = [eliminado.codigo_hmac, mantido.codigo_hmac]

    encerrar(cliente, estudo)

    registro = RegistroAuditoria.objects.get(acao=RegistroAuditoria.Acao.ELIMINACAO_ENCERRAMENTO)
    assert registro.usuario == pesquisadora and registro.criado_em
    assert estudo.nome in registro.objeto
    assert "Eliminados: 1" in registro.objeto and "Mantidos por outro estudo ativo: 1" in registro.objeto
    for codigo in codigos:
        assert codigo[:8] not in registro.objeto
    assert cpf_sintetico(1) not in registro.objeto and cpf_sintetico(2) not in registro.objeto


def test_registro_anonimo_nao_guarda_cpf_nem_codigo():
    campos = {campo.name for campo in RegistroAnonimo._meta.get_fields()}

    assert not {"voluntario", "codigo_voluntario", "codigo_hmac", "cpf_cifrado"} & campos


def test_painel_continua_com_os_mesmos_numeros_depois_da_eliminacao(
    cliente, pesquisadora, profissional, estudo
):
    regra = estudo.criterios.get()
    for numero in (1, 2):
        pessoa(profissional, estudo, numero, filhos=2)
    for numero in (3, 4):
        eliminado = Voluntario.objects.create(
            codigo_hmac=cpf.codigo(cpf_sintetico(numero)), cpf_cifrado=cpf.cifrar(cpf_sintetico(numero)),
            criado_por=profissional,
        )
        Participacao.objects.create(
            voluntario=eliminado, estudo=estudo, tcle_versao="1", registrado_por=profissional,
            situacao=Situacao.ELIMINADA, criterio_reprovado=regra,
        )
    DecisaoCandidato.objects.create(
        estudo=estudo, codigo_voluntario=Voluntario.objects.first().codigo_hmac, decisao=Decisao.INCLUIDO,
        decidido_por=pesquisadora, decidido_em=estudo.criado_em, classificacao_na_decisao="elegivel",
    )

    def linha():
        [linha] = dados_do_painel(pesquisadora)["estudos"]
        return linha["concluidos"], linha["eliminados"], linha["criterios"], dados_do_painel(pesquisadora)["semanas"]

    antes = linha()
    encerrar(cliente, estudo)

    assert Voluntario.objects.count() == 0 and Participacao.objects.count() == 0
    assert linha() == antes
    assert antes[0] == 2 and antes[1] == 2 and antes[2] == [{"frase": regra.frase, "total": 2}]
    assert RegistroAnonimo.objects.filter(incluido=True).count() == 1
    assert cliente.get(reverse("inicio")).status_code == 200


def test_recusa_do_RF12_usa_a_mesma_regra_e_mantem_quem_esta_em_outro_estudo_ativo(
    pesquisadora, profissional, estudo, outro_ativo
):
    voluntario = pessoa(profissional, outro_ativo, 1, filhos=2, cuidador=True)
    criterio(estudo, "cuidador_de_dependente", "verdadeiro")
    decisoes.incluir(estudo, [voluntario.id], pesquisadora)
    # Participação eliminada em outro estudo ativo também vincula, pela regra do RF13.
    outra = novo_estudo(pesquisadora, "Terceiro estudo ativo")
    vinculo(profissional, voluntario, outra, Situacao.ELIMINADA)
    outro_ativo.situacao = Estudo.Situacao.ENCERRADO
    outro_ativo.save()

    decisoes.recusar(estudo, [voluntario.id], pesquisadora)

    assert existe(voluntario)


class TestAcesso:
    @pytest.fixture
    def voluntario(self, profissional, estudo):
        return pessoa(profissional, estudo, 1, filhos=2)

    @pytest.mark.parametrize("metodo", ["get", "post"])
    def test_profissional_recebe_403_e_nada_muda(self, client, profissional, estudo, voluntario, metodo):
        client.force_login(profissional)

        resposta = getattr(client, metodo)(reverse("estudos:encerrar", args=[estudo.id]))

        estudo.refresh_from_db()
        assert resposta.status_code == 403
        assert estudo.situacao == Estudo.Situacao.ATIVO and existe(voluntario)

    @pytest.mark.parametrize("metodo", ["get", "post"])
    def test_outro_pesquisador_recebe_404_e_nada_muda(self, client, estudo, voluntario, metodo):
        outra = Usuario.objects.create_user(
            "outra@alunos.umc.br", "Outra Pesquisadora", "Senha!2026x", perfil=Usuario.Perfil.PESQUISADOR
        )
        client.force_login(outra)

        resposta = getattr(client, metodo)(reverse("estudos:encerrar", args=[estudo.id]))

        estudo.refresh_from_db()
        assert resposta.status_code == 404
        assert estudo.situacao == Estudo.Situacao.ATIVO and existe(voluntario)

    def test_anonimo_vai_para_o_login(self, client, estudo, voluntario):
        resposta = client.post(reverse("estudos:encerrar", args=[estudo.id]))

        estudo.refresh_from_db()
        assert resposta.status_code == 302 and resposta.url.startswith(reverse("login"))
        assert estudo.situacao == Estudo.Situacao.ATIVO and existe(voluntario)
