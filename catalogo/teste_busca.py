import pytest

from catalogo.busca import buscar_criterios
from catalogo.models import Categoria, SinonimoVariavel, Subcategoria, Variavel

pytestmark = pytest.mark.django_db


def rotulos(termo):
    return [variavel.rotulo for variavel in buscar_criterios(termo)]


def test_sinonimo_encontra_a_variavel():
    assert rotulos("grau de instrução") == ["Escolaridade"]


def test_busca_ignora_acento_e_caixa():
    assert rotulos("GRAU DE INSTRUCAO") == ["Escolaridade"]
    assert "Renda familiar" in rotulos("familia")


def test_busca_tolera_erro_de_digitacao():
    assert rotulos("escolaridde") == ["Escolaridade"]
    assert rotulos("heterosexual") == ["Orientação sexual"]


def test_busca_pelo_nome_curto():
    assert rotulos("per capita") == ["Renda per capita"]


def test_termo_com_varios_resultados_vem_do_mais_parecido():
    assert rotulos("renda") == ["Renda familiar", "Renda per capita"]


def test_termo_sem_correspondencia_nao_devolve_nada():
    assert rotulos("hemoglobina") == []


def test_termo_vazio_nao_devolve_nada():
    assert rotulos("") == []
    assert rotulos("   ") == []


def test_faixa_etaria_fica_fora_e_data_de_nascimento_entra():
    assert rotulos("faixa etária") == []
    assert "Data de nascimento" in rotulos("nascimento")


def test_variavel_de_texto_livre_fica_fora():
    categoria = Categoria.objects.create(codigo="TST", nome="Teste", ordem=9)
    subcategoria = Subcategoria.objects.create(categoria=categoria, codigo="OBS", nome="Observações", ordem=1)
    Variavel.objects.create(
        subcategoria=subcategoria, codigo="observacao_social", nome="Observação social", tipo=Variavel.Tipo.TEXTO
    )

    assert rotulos("observação") == []


def test_variavel_categorica_sem_dominio_fica_fora():
    categoria = Categoria.objects.create(codigo="TST", nome="Teste", ordem=9)
    subcategoria = Subcategoria.objects.create(categoria=categoria, codigo="REF", nome="Referência", ordem=1)
    Variavel.objects.create(
        subcategoria=subcategoria, codigo="cargo_na_tabela", nome="Cargo na tabela", tipo=Variavel.Tipo.NOMINAL,
        tabela_referencia="cbo",
    )

    assert rotulos("cargo na tabela") == []


def test_sinonimo_novo_passa_a_valer():
    escolaridade = Variavel.objects.get(codigo="escolaridade")
    SinonimoVariavel.objects.create(variavel=escolaridade, termo="anos de estudo")

    assert rotulos("anos de estudo") == ["Escolaridade"]


def test_resultado_traz_caminho_e_tipo():
    variavel = buscar_criterios("idade").first()

    assert variavel.caminho == "Perfil sociodemográfico › Identificação básica"
    assert variavel.tipo_resumido == "valor"


@pytest.mark.parametrize(
    "codigo, rotulo",
    [
        ("idade_anos", "valor"),
        ("orientacao_sexual", "opções"),
        ("escolaridade", "níveis"),
        ("cuidador_de_dependente", "sim ou não"),
    ],
)
def test_rotulo_de_tipo_mostrado_na_arvore(codigo, rotulo):
    assert Variavel.objects.get(codigo=codigo).tipo_resumido == rotulo


def test_pessoa_com_deficiencia_e_sensivel_e_achada_por_sinonimo():
    variavel = Variavel.objects.get(codigo="pessoa_com_deficiencia")

    assert variavel.sensivel
    assert variavel.tipo == Variavel.Tipo.BOOLEANA
    assert variavel.subcategoria.nome == "Identificação básica"
    for termo in ("PcD", "deficiente", "necessidades especiais"):
        assert "Pessoa com deficiência" in rotulos(termo)


def test_variaveis_sensiveis_do_catalogo():
    sensiveis = set(Variavel.objects.filter(sensivel=True).values_list("codigo", flat=True))

    assert sensiveis == {"identidade_genero", "orientacao_sexual", "raca_cor", "pessoa_com_deficiencia"}


def test_situacao_e_area_de_trabalho_tem_nomes_distintos():
    assert Variavel.objects.get(codigo="situacao_ocupacional").rotulo == "Situação de trabalho"
    assert Variavel.objects.get(codigo="ocupacao").rotulo == "Área de atuação profissional"


@pytest.mark.parametrize(
    "termo, esperado",
    [
        ("emprego", "Situação de trabalho"),
        ("situação ocupacional", "Situação de trabalho"),
        ("profissão", "Área de atuação profissional"),
        ("ocupação exercida", "Área de atuação profissional"),
        ("ramo de atividade", "Área de atuação profissional"),
    ],
)
def test_busca_pelo_termo_antigo_ou_pelo_sinonimo_acha_a_variavel_certa(termo, esperado):
    assert esperado in rotulos(termo)


def test_ocupacao_leva_as_duas_variaveis_para_o_pesquisador_escolher():
    assert {"Situação de trabalho", "Área de atuação profissional"} <= set(rotulos("ocupação"))


def test_situacao_de_trabalho_nao_e_achada_pela_profissao():
    assert "Situação de trabalho" not in rotulos("profissão")


def test_area_de_atuacao_e_uma_lista_fechada_sem_texto_livre():
    area = Variavel.objects.get(codigo="ocupacao")

    assert area.tipo == Variavel.Tipo.NOMINAL
    assert area.dominio.opcoes.count() == 19
    assert {"Saúde", "Educação", "Outra"} <= set(area.dominio.opcoes.values_list("rotulo", flat=True))
    assert area.tabela_referencia == ""
