from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0002_carga_do_catalogo")]

    operations = [
        migrations.RunSQL("DROP INDEX IF EXISTS catalogo_variavel_busca_trgm", migrations.RunSQL.noop),
    ]
