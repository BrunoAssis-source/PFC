from django.db import migrations

# Valor mais recente de cada variável por voluntário, mais as três variáveis derivadas. Idade, faixa etária e renda
# per capita não são gravadas: saem das origens a cada consulta, então a idade acompanha o calendário.
VALOR_EFETIVO = """
CREATE VIEW voluntarios_valor_efetivo AS
WITH atual AS (
    SELECT DISTINCT ON (codigo_voluntario, variavel_id)
        codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano
    FROM (
        SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano, coletado_em
        FROM voluntarios_valorcoletado
        UNION ALL
        SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano, coletado_em
        FROM voluntarios_valorsensivel
    ) todos
    ORDER BY codigo_voluntario, variavel_id, coletado_em DESC
),
idade AS (
    SELECT a.codigo_voluntario,
           date_part('year', age(current_date, a.valor_data))::numeric AS anos
    FROM atual a
    JOIN catalogo_variavel v ON v.id = a.variavel_id AND v.codigo = 'data_nascimento'
),
renda AS (
    SELECT r.codigo_voluntario,
           round(r.valor_numero / NULLIF(p.valor_numero, 0), 2) AS per_capita
    FROM atual r
    JOIN catalogo_variavel vr ON vr.id = r.variavel_id AND vr.codigo = 'renda_familiar_mensal'
    JOIN atual p ON p.codigo_voluntario = r.codigo_voluntario
    JOIN catalogo_variavel vp ON vp.id = p.variavel_id AND vp.codigo = 'pessoas_no_domicilio'
)
SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano FROM atual
UNION ALL
SELECT i.codigo_voluntario, v.id, i.anos, NULL::date, NULL::bigint, NULL::boolean
FROM idade i JOIN catalogo_variavel v ON v.codigo = 'idade_anos'
UNION ALL
SELECT i.codigo_voluntario, v.id, NULL::numeric, NULL::date, o.id, NULL::boolean
FROM idade i
JOIN catalogo_variavel v ON v.codigo = 'faixa_etaria'
JOIN catalogo_opcaodominio o ON o.dominio_id = v.dominio_id AND o.valor = CASE
    WHEN i.anos < 18 THEN 'ate_17'
    WHEN i.anos < 30 THEN '18_29'
    WHEN i.anos < 40 THEN '30_39'
    WHEN i.anos < 50 THEN '40_49'
    WHEN i.anos < 60 THEN '50_59'
    WHEN i.anos < 70 THEN '60_69'
    ELSE '70_mais' END
UNION ALL
SELECT r.codigo_voluntario, v.id, r.per_capita, NULL::date, NULL::bigint, NULL::boolean
FROM renda r JOIN catalogo_variavel v ON v.codigo = 'renda_per_capita'
WHERE r.per_capita IS NOT NULL
"""

# Uma linha por participação, critério do estudo e variável já respondida. Critério sem resposta não aparece.
# cumpre vale para inclusão quando o voluntário atende e para exclusão quando não atende.
AVALIACAO = """
CREATE VIEW voluntarios_avaliacao_criterio AS
SELECT participacao_id, criterio_id, variavel_id,
       CASE tipo_regra WHEN 'inclusao' THEN atende ELSE NOT atende END AS cumpre
FROM (
    SELECT p.id AS participacao_id, c.id AS criterio_id, c.variavel_id, c.tipo_regra,
           CASE c.operador
               WHEN 'igual' THEN e.valor_numero = c.valor_numero
               WHEN 'diferente' THEN e.valor_numero <> c.valor_numero
               WHEN 'menor' THEN e.valor_numero < c.valor_numero
               WHEN 'maior' THEN e.valor_numero > c.valor_numero
               WHEN 'menor_igual' THEN
                   CASE WHEN v.tipo = 'ordinal' THEN o.ordem <= sel.maxima ELSE e.valor_numero <= c.valor_numero END
               WHEN 'maior_igual' THEN
                   CASE WHEN v.tipo = 'ordinal' THEN o.ordem >= sel.minima ELSE e.valor_numero >= c.valor_numero END
               WHEN 'entre' THEN
                   CASE v.tipo
                       WHEN 'numerica' THEN e.valor_numero BETWEEN c.valor_numero AND c.valor_numero_ate
                       WHEN 'data' THEN e.valor_data BETWEEN c.valor_data AND c.valor_data_ate
                       ELSE o.ordem BETWEEN sel.minima AND sel.maxima
                   END
               WHEN 'e' THEN e.opcao_id = ANY (sel.ids)
               WHEN 'esta_em' THEN e.opcao_id = ANY (sel.ids)
               WHEN 'nao_e' THEN NOT (e.opcao_id = ANY (sel.ids))
               WHEN 'nao_esta_em' THEN NOT (e.opcao_id = ANY (sel.ids))
               WHEN 'verdadeiro' THEN e.valor_booleano IS TRUE
               WHEN 'falso' THEN e.valor_booleano IS FALSE
               WHEN 'antes' THEN e.valor_data < c.valor_data
               WHEN 'depois' THEN e.valor_data > c.valor_data
           END AS atende
    FROM voluntarios_participacao p
    JOIN voluntarios_voluntario vol ON vol.id = p.voluntario_id
    JOIN estudos_criterio c ON c.estudo_id = p.estudo_id
    JOIN catalogo_variavel v ON v.id = c.variavel_id
    JOIN voluntarios_valor_efetivo e
         ON e.codigo_voluntario = vol.codigo_hmac AND e.variavel_id = c.variavel_id
    LEFT JOIN catalogo_opcaodominio o ON o.id = e.opcao_id
    LEFT JOIN LATERAL (
        SELECT array_agg(od.id) AS ids, min(od.ordem) AS minima, max(od.ordem) AS maxima
        FROM estudos_criterio_opcoes co
        JOIN catalogo_opcaodominio od ON od.id = co.opcaodominio_id
        WHERE co.criterio_id = c.id
    ) sel ON true
) avaliados
"""


class Migration(migrations.Migration):
    dependencies = [
        ("voluntarios", "0002_coleta_de_valores"),
        ("estudos", "0002_tipo_regra"),
        ("catalogo", "0013_texto_da_resposta_de_pessoa_com_deficiencia"),
    ]

    operations = [
        migrations.RunSQL(VALOR_EFETIVO, "DROP VIEW voluntarios_valor_efetivo"),
        migrations.RunSQL(AVALIACAO, "DROP VIEW voluntarios_avaliacao_criterio"),
    ]
