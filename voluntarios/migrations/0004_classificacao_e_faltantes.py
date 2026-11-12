import importlib

from django.db import migrations

anterior = importlib.import_module("voluntarios.migrations.0003_views_de_verificacao")

# Igual à da migration 0003, com um acréscimo: o valor mais recente de uma variável só vale dentro da vida útil dela.
# Valor vencido conta como ausente, sem voltar a um valor mais antigo. Idade, faixa etária e renda per capita saem
# das origens válidas, então uma origem vencida também deixa a derivada sem valor.
VALOR_EFETIVO = """
CREATE VIEW voluntarios_valor_efetivo AS
WITH recente AS (
    SELECT DISTINCT ON (codigo_voluntario, variavel_id)
        codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano, coletado_em
    FROM (
        SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano, coletado_em
        FROM voluntarios_valorcoletado
        UNION ALL
        SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano, coletado_em
        FROM voluntarios_valorsensivel
    ) todos
    ORDER BY codigo_voluntario, variavel_id, coletado_em DESC
),
atual AS (
    SELECT r.codigo_voluntario, r.variavel_id, r.valor_numero, r.valor_data, r.opcao_id, r.valor_booleano
    FROM recente r
    JOIN catalogo_variavel cv ON cv.id = r.variavel_id
    WHERE cv.vida_util_dias IS NULL OR r.coletado_em + make_interval(days => cv.vida_util_dias) >= now()
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

# Uma linha por voluntário, critério e variável já respondida, sem depender de participação. É a verificação dos 15
# operadores da RF09, agora também usada na classificação. Critério sem valor não aparece.
AVALIACAO_POR_PAR = """
CREATE VIEW voluntarios_avaliacao_par AS
SELECT voluntario_id, estudo_id, criterio_id, variavel_id,
       CASE tipo_regra WHEN 'inclusao' THEN atende ELSE NOT atende END AS cumpre
FROM (
    SELECT vol.id AS voluntario_id, c.estudo_id, c.id AS criterio_id, c.variavel_id, c.tipo_regra,
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
    FROM voluntarios_voluntario vol
    CROSS JOIN estudos_criterio c
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

# A view que a coleta já usava, agora como junção da participação com a avaliação por par.
AVALIACAO_POR_PARTICIPACAO = """
CREATE VIEW voluntarios_avaliacao_criterio AS
SELECT p.id AS participacao_id, a.criterio_id, a.variavel_id, a.cumpre
FROM voluntarios_participacao p
JOIN voluntarios_avaliacao_par a ON a.voluntario_id = p.voluntario_id AND a.estudo_id = p.estudo_id
"""

# Variáveis que ainda faltam para avaliar todos os critérios de um estudo. A derivada entra pelas origens, e só
# a origem sem valor válido conta como faltante. Uma linha por voluntário, estudo e variável.
FALTANTES = """
CREATE VIEW voluntarios_faltantes AS
WITH RECURSIVE alvo(estudo_id, variavel_id) AS (
    SELECT estudo_id, variavel_id FROM estudos_criterio
    UNION
    SELECT a.estudo_id, o.to_variavel_id
    FROM alvo a JOIN catalogo_variavel_origem o ON o.from_variavel_id = a.variavel_id
)
SELECT vol.id AS voluntario_id, a.estudo_id, a.variavel_id
FROM alvo a
JOIN catalogo_variavel cv ON cv.id = a.variavel_id AND NOT cv.derivada
CROSS JOIN voluntarios_voluntario vol
WHERE NOT EXISTS (
    SELECT 1 FROM voluntarios_valor_efetivo e
    WHERE e.codigo_voluntario = vol.codigo_hmac AND e.variavel_id = a.variavel_id
)
"""

# RN26 para cada par de voluntário e estudo ativo. Inelegível: reprova em algum critério, mesmo faltando outros
# valores, ou teve a coleta encerrada por critério. Elegível: todos os critérios avaliados e nenhum reprovado.
# Pendente: nenhum reprovado, mas falta valor. registrado diz se o voluntário já tem algum valor válido na base.
CLASSIFICACAO = """
CREATE VIEW voluntarios_classificacao AS
SELECT vol.id AS voluntario_id, e.id AS estudo_id,
       CASE
           WHEN part.situacao = 'eliminada' OR COALESCE(r.reprovados, 0) > 0 THEN 'inelegivel'
           WHEN COALESCE(r.avaliados, 0) = t.total THEN 'elegivel'
           ELSE 'pendente'
       END AS classe,
       EXISTS (
           SELECT 1 FROM voluntarios_valor_efetivo ve WHERE ve.codigo_voluntario = vol.codigo_hmac
       ) AS registrado
FROM voluntarios_voluntario vol
CROSS JOIN estudos_estudo e
JOIN LATERAL (SELECT count(*) AS total FROM estudos_criterio WHERE estudo_id = e.id) t ON true
LEFT JOIN LATERAL (
    SELECT count(*) AS avaliados, count(*) FILTER (WHERE NOT cumpre) AS reprovados
    FROM voluntarios_avaliacao_par
    WHERE voluntario_id = vol.id AND estudo_id = e.id
) r ON true
LEFT JOIN voluntarios_participacao part ON part.voluntario_id = vol.id AND part.estudo_id = e.id
WHERE e.situacao = 'ativo'
"""


class Migration(migrations.Migration):
    dependencies = [("voluntarios", "0003_views_de_verificacao")]

    operations = [
        migrations.RunSQL("DROP VIEW voluntarios_avaliacao_criterio", anterior.AVALIACAO),
        migrations.RunSQL("DROP VIEW voluntarios_valor_efetivo", anterior.VALOR_EFETIVO),
        migrations.RunSQL(VALOR_EFETIVO, "DROP VIEW voluntarios_valor_efetivo"),
        migrations.RunSQL(AVALIACAO_POR_PAR, "DROP VIEW voluntarios_avaliacao_par"),
        migrations.RunSQL(AVALIACAO_POR_PARTICIPACAO, "DROP VIEW voluntarios_avaliacao_criterio"),
        migrations.RunSQL(FALTANTES, "DROP VIEW voluntarios_faltantes"),
        migrations.RunSQL(CLASSIFICACAO, "DROP VIEW voluntarios_classificacao"),
    ]
