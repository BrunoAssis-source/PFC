import importlib

from django.db import migrations

base = importlib.import_module("voluntarios.migrations.0004_classificacao_e_faltantes")

# O relógio do Windows avança em saltos de alguns milissegundos, então dois valores gravados em seguida podem ter o
# mesmo coletado_em e o DISTINCT ON escolhia qualquer um. Agora desempata pelo id e, se o id também coincidir por
# serem tabelas diferentes, pela tabela. Só a ordem muda, as colunas da view continuam as mesmas.
ORIGENS = (
    ("FROM voluntarios_valorcoletado", "0"),
    ("FROM voluntarios_valorsensivel", "1"),
)
VALOR_EFETIVO = base.VALOR_EFETIVO
for origem, tabela in ORIGENS:
    antes = f"coletado_em\n        {origem}"
    assert VALOR_EFETIVO.count(antes) == 1
    VALOR_EFETIVO = VALOR_EFETIVO.replace(antes, f"coletado_em, id, {tabela} AS tabela\n        {origem}")
ORDEM = "ORDER BY codigo_voluntario, variavel_id, coletado_em DESC"
assert VALOR_EFETIVO.count(ORDEM) == 1
VALOR_EFETIVO = VALOR_EFETIVO.replace(ORDEM, ORDEM + ", id DESC, tabela DESC")


class Migration(migrations.Migration):
    # O PostgreSQL não deixa trocar uma view de que outra depende. As cinco são derrubadas de cima para baixo e
    # recriadas na mesma ordem em que a 0004 as criou.
    dependencies = [("voluntarios", "0005_pendencia_notificada")]

    operations = [
        migrations.RunSQL("DROP VIEW voluntarios_classificacao", base.CLASSIFICACAO),
        migrations.RunSQL("DROP VIEW voluntarios_faltantes", base.FALTANTES),
        migrations.RunSQL("DROP VIEW voluntarios_avaliacao_criterio", base.AVALIACAO_POR_PARTICIPACAO),
        migrations.RunSQL("DROP VIEW voluntarios_avaliacao_par", base.AVALIACAO_POR_PAR),
        migrations.RunSQL("DROP VIEW voluntarios_valor_efetivo", base.VALOR_EFETIVO),
        migrations.RunSQL(VALOR_EFETIVO, "DROP VIEW voluntarios_valor_efetivo"),
        migrations.RunSQL(base.AVALIACAO_POR_PAR, "DROP VIEW voluntarios_avaliacao_par"),
        migrations.RunSQL(base.AVALIACAO_POR_PARTICIPACAO, "DROP VIEW voluntarios_avaliacao_criterio"),
        migrations.RunSQL(base.FALTANTES, "DROP VIEW voluntarios_faltantes"),
        migrations.RunSQL(base.CLASSIFICACAO, "DROP VIEW voluntarios_classificacao"),
    ]
