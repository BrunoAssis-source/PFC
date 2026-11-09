from django.db import migrations

from catalogo.models import Variavel as VariavelAtual

CODIGO = "pessoa_com_deficiencia"
NOME = "Pessoa com deficiência"
SINONIMOS = ["PcD", "deficiente", "deficiência", "necessidades especiais", "acessibilidade"]


def aplicar(apps, schema_editor):
    Subcategoria = apps.get_model("catalogo", "Subcategoria")
    Variavel = apps.get_model("catalogo", "Variavel")
    Sinonimo = apps.get_model("catalogo", "SinonimoVariavel")

    # Dado de saúde, então sensível, como identidade de gênero e orientação sexual.
    variavel = Variavel.objects.create(
        subcategoria=Subcategoria.objects.get(categoria__codigo="SOC", codigo="IDN"),
        codigo=CODIGO,
        nome=NOME,
        nome_curto=NOME,
        tipo="booleana",
        definicao="Se o participante tem deficiência física, sensorial, intelectual ou psicossocial, autodeclarada.",
        sensivel=True,
        vida_util_dias=1825,
        busca=VariavelAtual.texto_de_busca(NOME, CODIGO),
    )
    for termo in SINONIMOS:
        Sinonimo.objects.create(variavel=variavel, termo=termo)


def desfazer(apps, schema_editor):
    apps.get_model("catalogo", "Variavel").objects.filter(codigo=CODIGO).delete()


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0009_estados_e_municipios_do_ibge")]

    operations = [migrations.RunPython(aplicar, desfazer)]
