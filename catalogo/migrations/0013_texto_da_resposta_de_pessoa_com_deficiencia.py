from django.db import migrations


def aplicar(apps, schema_editor):
    apps.get_model("catalogo", "Variavel").objects.filter(codigo="pessoa_com_deficiencia").update(
        texto_sim="com deficiência", texto_nao="sem deficiência"
    )


def desfazer(apps, schema_editor):
    apps.get_model("catalogo", "Variavel").objects.filter(codigo="pessoa_com_deficiencia").update(
        texto_sim="", texto_nao=""
    )


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0012_texto_da_resposta")]

    operations = [migrations.RunPython(aplicar, desfazer)]
