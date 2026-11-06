from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0003_remove_indice_busca")]

    operations = [UnaccentExtension(), TrigramExtension()]
