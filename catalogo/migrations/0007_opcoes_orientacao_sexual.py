from django.db import migrations

# Mesma lista do protótipo da tela de critérios, na ordem em que aparece.
OPCOES = [
    ("heterossexual", "Heterossexual"), ("gay_lesbica", "Gay ou lésbica"),
    ("bissexual", "Bissexual"), ("pansexual", "Pansexual"), ("assexual", "Assexual"),
    ("outra", "Outra"), ("nao_responder", "Prefiro não responder"),
]


def aplicar(apps, schema_editor):
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    dominio = apps.get_model("catalogo", "Dominio").objects.get(codigo="orientacao_sexual")
    dominio.opcoes.all().delete()
    for posicao, (valor, rotulo) in enumerate(OPCOES, start=1):
        OpcaoDominio.objects.create(dominio=dominio, valor=valor, rotulo=rotulo, ordem=posicao)


def desfazer(apps, schema_editor):
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    dominio = apps.get_model("catalogo", "Dominio").objects.get(codigo="orientacao_sexual")
    dominio.opcoes.all().delete()
    anteriores = [
        ("heterossexual", "Heterossexual"), ("homossexual", "Homossexual"),
        ("bissexual", "Bissexual"), ("outra", "Outra"), ("nao_responder", "Prefiro não responder"),
    ]
    for posicao, (valor, rotulo) in enumerate(anteriores, start=1):
        OpcaoDominio.objects.create(dominio=dominio, valor=valor, rotulo=rotulo, ordem=posicao)


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0006_nomes_curtos_sinonimos_e_variaveis")]

    operations = [migrations.RunPython(aplicar, desfazer)]
