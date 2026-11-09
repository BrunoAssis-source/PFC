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


def test_data_de_nascimento_e_faixa_etaria_ficam_fora():
    assert rotulos("nascimento") == []
    assert rotulos("faixa etária") == []


def test_variavel_de_texto_livre_fica_fora():
    categoria = Categoria.objects.create(codigo="TST", nome="Teste", ordem=9)
    subcategoria = Subcategoria.objects.create(categoria=categoria, codigo="OBS", nome="Observações", ordem=1)
    Variavel.objects.create(
        subcategoria=subcategoria, codigo="observacao_social", nome="Observação social", tipo=Variavel.Tipo.TEXTO
    )

    assert rotulos("observação") == []


def test_variavel_categorica_sem_dominio_fica_fora():
    # A ocupação depende de uma tabela da CBO que não existe no sistema.
    assert "Ocupação" not in rotulos("profissão")


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
