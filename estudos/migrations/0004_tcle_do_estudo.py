import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estudos', '0003_prazo_de_guarda_e_acoes'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tcle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome_arquivo', models.CharField(max_length=255, verbose_name='nome do arquivo')),
                ('conteudo', models.BinaryField(verbose_name='conteúdo')),
                ('enviado_em', models.DateTimeField(auto_now=True, verbose_name='enviado em')),
                ('estudo', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='tcle', to='estudos.estudo')),
            ],
            options={
                'verbose_name': 'TCLE',
                'verbose_name_plural': 'TCLEs',
            },
        ),
    ]
