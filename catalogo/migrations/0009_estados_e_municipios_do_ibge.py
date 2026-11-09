import csv
from pathlib import Path

from django.db import migrations

from catalogo.models import Variavel as VariavelAtual

DADOS = Path(__file__).resolve().parent.parent / "dados"


def linhas(arquivo):
    with open(DADOS / arquivo, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def aplicar(apps, schema_editor):
    Dominio = apps.get_model("catalogo", "Dominio")
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    Variavel = apps.get_model("catalogo", "Variavel")
    Sinonimo = apps.get_model("catalogo", "SinonimoVariavel")

    estados = Dominio.objects.create(codigo="uf", nome="Estado, segundo o IBGE")
    municipios = Dominio.objects.create(codigo="municipio", nome="Município, segundo o IBGE", superior=estados)

    por_sigla = {}
    for posicao, linha in enumerate(linhas("ufs_ibge.csv"), start=1):
        por_sigla[linha["sigla"]] = OpcaoDominio.objects.create(
            dominio=estados, valor=linha["sigla"].lower(), rotulo=linha["nome"], ordem=posicao
        )

    # O valor guarda o código do IBGE, que não repete. O rótulo leva a sigla
    # porque há nomes iguais em estados diferentes, e a frase do critério
    # precisa dizer de qual se trata.
    # A ordem segue o arquivo, por sigla do estado e depois por nome.
    novas = []
    for ordem, linha in enumerate(linhas("municipios_ibge.csv"), start=1):
        novas.append(OpcaoDominio(
            dominio=municipios, pai=por_sigla[linha["uf"]], valor=linha["codigo"],
            rotulo=f'{linha["nome"]} ({linha["uf"]})', ordem=ordem,
        ))
    OpcaoDominio.objects.bulk_create(novas, batch_size=1000)

    municipio = Variavel.objects.get(codigo="municipio_residencia")
    municipio.dominio, municipio.tabela_referencia = municipios, ""
    municipio.nome, municipio.nome_curto = "Município de residência", "Município de residência"
    municipio.definicao = "Município onde o participante mora no momento da coleta."
    municipio.busca = VariavelAtual.texto_de_busca(municipio.nome, municipio.codigo)
    municipio.save()

    estado = Variavel.objects.get(codigo="uf_residencia")
    estado.dominio, estado.tabela_referencia, estado.derivada = estados, "", False
    estado.origem.clear()
    estado.nome, estado.nome_curto = "Estado de residência", "Estado de residência"
    estado.definicao = "Estado onde o participante mora no momento da coleta."
    estado.vida_util_dias = 730
    estado.busca = VariavelAtual.texto_de_busca(estado.nome, estado.codigo)
    estado.save()

    for variavel, termos in ((municipio, ["município", "localidade"]), (estado, ["unidade federativa"])):
        for termo in termos:
            Sinonimo.objects.get_or_create(variavel=variavel, termo=termo)


def desfazer(apps, schema_editor):
    Dominio = apps.get_model("catalogo", "Dominio")
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    Variavel = apps.get_model("catalogo", "Variavel")
    Sinonimo = apps.get_model("catalogo", "SinonimoVariavel")

    municipio = Variavel.objects.get(codigo="municipio_residencia")
    municipio.dominio, municipio.tabela_referencia = None, "ibge_municipio"
    municipio.nome, municipio.nome_curto = "Município onde mora atualmente", "Município"
    municipio.definicao = "Município de residência no momento da coleta, pela tabela do IBGE."
    municipio.busca = VariavelAtual.texto_de_busca(municipio.nome, municipio.codigo)
    municipio.save()

    estado = Variavel.objects.get(codigo="uf_residencia")
    estado.dominio, estado.tabela_referencia, estado.derivada = None, "ibge_uf", True
    estado.origem.set([municipio])
    estado.nome, estado.nome_curto = "Unidade federativa de residência", "Estado (UF)"
    estado.definicao = "Derivada do município informado, pela tabela do IBGE."
    estado.vida_util_dias = None
    estado.busca = VariavelAtual.texto_de_busca(estado.nome, estado.codigo)
    estado.save()

    Sinonimo.objects.filter(variavel__in=[municipio, estado], termo__in=["município", "localidade", "unidade federativa"]).delete()
    OpcaoDominio.objects.filter(dominio__codigo="municipio").delete()
    OpcaoDominio.objects.filter(dominio__codigo="uf").delete()
    Dominio.objects.filter(codigo="municipio").delete()
    Dominio.objects.filter(codigo="uf").delete()


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0008_dominio_superior_e_opcao_pai")]

    operations = [migrations.RunPython(aplicar, desfazer)]
