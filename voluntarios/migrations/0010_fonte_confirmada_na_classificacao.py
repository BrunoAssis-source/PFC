import importlib

from django.db import migrations

base = importlib.import_module("voluntarios.migrations.0004_classificacao_e_faltantes")
desempate = importlib.import_module("voluntarios.migrations.0006_desempate_do_valor_mais_recente")


def _trocar(sql, antes, depois, vezes=1):
    assert sql.count(antes) == vezes, antes
    return sql.replace(antes, depois)


# Valor informado só pelo voluntário não é fonte confirmada. Para os estudos que reaproveitam o dado ele conta como
# ausente (pendente), e vale sem ressalva no estudo em que foi coletado, onde a verificação é eliminatória. Documento
# e prontuário valem em qualquer estudo. A view passa a expor a fonte e a participação de cada valor, e as derivadas
# herdam a da origem. A renda per capita só vale pela participação quando as duas origens vêm da mesma.
VALOR_EFETIVO = desempate.VALOR_EFETIVO
for antes, depois in (
    ("coletado_em, id, 0 AS tabela\n", "coletado_em, id, 0 AS tabela, fonte, participacao_id\n"),
    ("coletado_em, id, 1 AS tabela\n", "coletado_em, id, 1 AS tabela, fonte, participacao_id\n"),
    (
        "valor_booleano, coletado_em\n    FROM (",
        "valor_booleano, coletado_em, fonte, participacao_id\n    FROM (",
    ),
    (
        "r.valor_booleano\n    FROM recente r",
        "r.valor_booleano, r.fonte, r.participacao_id\n    FROM recente r",
    ),
    (
        "date_part('year', age(current_date, a.valor_data))::numeric AS anos\n",
        "date_part('year', age(current_date, a.valor_data))::numeric AS anos,\n           a.fonte, a.participacao_id\n",
    ),
    (
        "round(r.valor_numero / NULLIF(p.valor_numero, 0), 2) AS per_capita\n",
        "round(r.valor_numero / NULLIF(p.valor_numero, 0), 2) AS per_capita,\n"
        "           CASE WHEN r.fonte <> 'voluntario' AND p.fonte <> 'voluntario' THEN 'documento' ELSE 'voluntario' END AS fonte,\n"
        "           CASE WHEN r.participacao_id = p.participacao_id THEN r.participacao_id END AS participacao_id\n",
    ),
    (
        "SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano FROM atual",
        "SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano, fonte, participacao_id FROM atual",
    ),
    ("NULL::bigint, NULL::boolean\nFROM idade i JOIN", "NULL::bigint, NULL::boolean, i.fonte, i.participacao_id\nFROM idade i JOIN"),
    ("o.id, NULL::boolean\nFROM idade i\n", "o.id, NULL::boolean, i.fonte, i.participacao_id\nFROM idade i\n"),
    ("NULL::bigint, NULL::boolean\nFROM renda r", "NULL::bigint, NULL::boolean, r.fonte, r.participacao_id\nFROM renda r"),
):
    VALOR_EFETIVO = _trocar(VALOR_EFETIVO, antes, depois)

CONFIRMADO = "(e.fonte <> 'voluntario' OR EXISTS (SELECT 1 FROM voluntarios_participacao pe WHERE pe.id = e.participacao_id AND pe.estudo_id = {estudo}))"

AVALIACAO_POR_PAR = _trocar(
    base.AVALIACAO_POR_PAR,
    "ON e.codigo_voluntario = vol.codigo_hmac AND e.variavel_id = c.variavel_id\n",
    "ON e.codigo_voluntario = vol.codigo_hmac AND e.variavel_id = c.variavel_id\n         AND "
    + CONFIRMADO.format(estudo="c.estudo_id")
    + "\n",
)

FALTANTES = _trocar(
    base.FALTANTES,
    "WHERE e.codigo_voluntario = vol.codigo_hmac AND e.variavel_id = a.variavel_id\n",
    "WHERE e.codigo_voluntario = vol.codigo_hmac AND e.variavel_id = a.variavel_id\n      AND "
    + CONFIRMADO.format(estudo="a.estudo_id")
    + "\n",
)


class Migration(migrations.Migration):
    # Mesma ordem da 0006: derruba de cima para baixo e recria de baixo para cima. A classificação e a avaliação por
    # participação não mudam de texto, mas dependem das views alteradas.
    dependencies = [("voluntarios", "0009_valores_sem_participacao_obrigatoria")]

    operations = [
        migrations.RunSQL("DROP VIEW voluntarios_classificacao", base.CLASSIFICACAO),
        migrations.RunSQL("DROP VIEW voluntarios_faltantes", base.FALTANTES),
        migrations.RunSQL("DROP VIEW voluntarios_avaliacao_criterio", base.AVALIACAO_POR_PARTICIPACAO),
        migrations.RunSQL("DROP VIEW voluntarios_avaliacao_par", base.AVALIACAO_POR_PAR),
        migrations.RunSQL("DROP VIEW voluntarios_valor_efetivo", desempate.VALOR_EFETIVO),
        migrations.RunSQL(VALOR_EFETIVO, "DROP VIEW voluntarios_valor_efetivo"),
        migrations.RunSQL(AVALIACAO_POR_PAR, "DROP VIEW voluntarios_avaliacao_par"),
        migrations.RunSQL(base.AVALIACAO_POR_PARTICIPACAO, "DROP VIEW voluntarios_avaliacao_criterio"),
        migrations.RunSQL(FALTANTES, "DROP VIEW voluntarios_faltantes"),
        migrations.RunSQL(base.CLASSIFICACAO, "DROP VIEW voluntarios_classificacao"),
    ]
