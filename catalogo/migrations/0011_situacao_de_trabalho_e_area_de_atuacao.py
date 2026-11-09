from django.db import migrations

from catalogo.models import Variavel as VariavelAtual

# O código interno de cada variável não muda: critérios já salvos apontam para
# o registro, e o pesquisador nunca vê o código.
SITUACAO = "situacao_ocupacional"
AREA = "ocupacao"

AREAS = [
    ("administracao_escritorio", "Administração e escritório"),
    ("agropecuaria", "Agropecuária e meio ambiente"),
    ("alimentacao_hospedagem", "Alimentação e hospedagem"),
    ("artes_comunicacao", "Artes, comunicação e esportes"),
    ("comercio_vendas", "Comércio e vendas"),
    ("construcao_civil", "Construção civil"),
    ("educacao", "Educação"),
    ("financas_contabilidade", "Finanças e contabilidade"),
    ("industria", "Indústria e produção"),
    ("juridica", "Área jurídica"),
    ("limpeza_domesticos", "Limpeza e serviços domésticos"),
    ("manutencao_reparos", "Manutenção e reparos"),
    ("administracao_publica", "Administração pública"),
    ("saude", "Saúde"),
    ("seguranca_defesa", "Segurança e defesa"),
    ("tecnologia", "Tecnologia da informação"),
    ("transporte_logistica", "Transporte e logística"),
    ("outra", "Outra"),
    ("nao_responder", "Prefiro não responder"),
]

# "ocupação" fica nas duas de propósito: quem procura por ele vê as duas e escolhe.
SINONIMOS = {
    SITUACAO: ["ocupação", "situação ocupacional", "vínculo de trabalho", "carteira assinada"],
    AREA: ["ocupação", "ocupação exercida", "área de atuação", "ramo de atividade", "setor de trabalho"],
}


def gravar(Variavel, codigo, **campos):
    variavel = Variavel.objects.get(codigo=codigo)
    for campo, valor in campos.items():
        setattr(variavel, campo, valor)
    variavel.busca = VariavelAtual.texto_de_busca(variavel.nome, variavel.codigo)
    variavel.save()
    return variavel


def aplicar(apps, schema_editor):
    Dominio = apps.get_model("catalogo", "Dominio")
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    Variavel = apps.get_model("catalogo", "Variavel")
    Sinonimo = apps.get_model("catalogo", "SinonimoVariavel")

    Dominio.objects.filter(codigo="situacao_ocupacional").update(nome="Situação de trabalho")
    areas = Dominio.objects.create(codigo="area_atuacao", nome="Área de atuação profissional")
    for posicao, (valor, rotulo) in enumerate(AREAS, start=1):
        OpcaoDominio.objects.create(dominio=areas, valor=valor, rotulo=rotulo, ordem=posicao)

    gravar(
        Variavel, SITUACAO,
        nome="Situação de trabalho atual", nome_curto="Situação de trabalho",
        definicao="Se o participante trabalha no momento da coleta e de que forma.",
    )
    gravar(
        Variavel, AREA,
        nome="Área de atuação profissional", nome_curto="Área de atuação profissional",
        definicao="Campo em que o participante trabalha, qualquer que seja o cargo.",
        dominio=areas, tabela_referencia="",
    )
    for codigo, termos in SINONIMOS.items():
        for termo in termos:
            Sinonimo.objects.get_or_create(variavel=Variavel.objects.get(codigo=codigo), termo=termo)


def desfazer(apps, schema_editor):
    Dominio = apps.get_model("catalogo", "Dominio")
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    Variavel = apps.get_model("catalogo", "Variavel")
    Sinonimo = apps.get_model("catalogo", "SinonimoVariavel")

    for codigo, termos in SINONIMOS.items():
        Sinonimo.objects.filter(variavel__codigo=codigo, termo__in=termos).delete()
    gravar(
        Variavel, AREA,
        nome="Ocupação exercida", nome_curto="Ocupação",
        definicao="Ocupação principal, pela Classificação Brasileira de Ocupações.",
        dominio=None, tabela_referencia="cbo",
    )
    gravar(
        Variavel, SITUACAO,
        nome="Situação ocupacional atual", nome_curto="Situação ocupacional",
        definicao="Vínculo de trabalho do participante no momento da coleta.",
    )
    OpcaoDominio.objects.filter(dominio__codigo="area_atuacao").delete()
    Dominio.objects.filter(codigo="area_atuacao").delete()
    Dominio.objects.filter(codigo="situacao_ocupacional").update(nome="Situação ocupacional")


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0010_pessoa_com_deficiencia")]

    operations = [migrations.RunPython(aplicar, desfazer)]
