from django.db import migrations

from catalogo.models import Variavel as VariavelAtual

DOMINIOS = [
    ("sexo_ao_nascer", "Sexo ao nascer", False, [
        ("feminino", "Feminino"), ("masculino", "Masculino"), ("intersexo", "Intersexo"),
    ]),
    ("identidade_genero", "Identidade de gênero", False, [
        ("mulher_cis", "Mulher cisgênero"), ("homem_cis", "Homem cisgênero"),
        ("mulher_trans", "Mulher transgênero"), ("homem_trans", "Homem transgênero"),
        ("nao_binario", "Não binário"), ("nao_responder", "Prefiro não responder"),
    ]),
    ("raca_cor", "Raça ou cor, classificação do IBGE", False, [
        ("branca", "Branca"), ("preta", "Preta"), ("parda", "Parda"),
        ("amarela", "Amarela"), ("indigena", "Indígena"),
    ]),
    ("zona_residencia", "Zona de residência", False, [
        ("urbana", "Urbana"), ("rural", "Rural"),
    ]),
    ("escolaridade", "Escolaridade", True, [
        ("sem_instrucao", "Sem instrução"),
        ("fundamental_incompleto", "Fundamental incompleto"),
        ("fundamental_completo", "Fundamental completo"),
        ("medio_incompleto", "Médio incompleto"),
        ("medio_completo", "Médio completo"),
        ("superior_incompleto", "Superior incompleto"),
        ("superior_completo", "Superior completo"),
        ("pos_graduacao", "Pós-graduação"),
    ]),
    ("situacao_ocupacional", "Situação ocupacional", False, [
        ("empregado_com_registro", "Empregado com registro"),
        ("empregado_sem_registro", "Empregado sem registro"),
        ("autonomo", "Autônomo"), ("desempregado", "Desempregado"),
        ("aposentado", "Aposentado"), ("estudante", "Estudante"),
        ("domestico_nao_remunerado", "Trabalho doméstico não remunerado"),
        ("afastado", "Afastado"),
    ]),
    ("beneficio_social", "Benefício social recebido", False, [
        ("transferencia_renda", "Transferência de renda federal"),
        ("bpc", "Benefício de prestação continuada"),
        ("seguro_desemprego", "Seguro-desemprego"),
        ("nenhum", "Nenhum"),
    ]),
    ("posse_domicilio", "Posse do domicílio", False, [
        ("proprio_quitado", "Próprio quitado"), ("proprio_financiado", "Próprio financiado"),
        ("alugado", "Alugado"), ("cedido", "Cedido"),
    ]),
    ("estado_civil", "Estado civil", False, [
        ("solteiro", "Solteiro"), ("casado_uniao", "Casado ou união estável"),
        ("separado", "Separado ou divorciado"), ("viuvo", "Viúvo"),
    ]),
    ("faixa_etaria", "Faixa etária", True, [
        ("ate_17", "Até 17 anos"), ("18_29", "18 a 29 anos"), ("30_39", "30 a 39 anos"),
        ("40_49", "40 a 49 anos"), ("50_59", "50 a 59 anos"), ("60_69", "60 a 69 anos"),
        ("70_mais", "70 anos ou mais"),
    ]),
]

SUBCATEGORIAS = [
    ("IDN", "Identificação básica", 1),
    ("LOC", "Localização", 2),
    ("DOM", "Domicílio, renda, escolaridade e ocupação", 3),
    ("FAM", "Composição familiar", 4),
]

# O nome diz período, momento de referência e abrangência, e a definição
# completa o que o nome não comporta.
VARIAVEIS = [
    ("IDN", "data_nascimento", "data", "Data de nascimento",
     "Data de nascimento declarada pelo participante.", {}),
    ("IDN", "sexo_ao_nascer", "nominal", "Sexo ao nascer",
     "Sexo registrado no nascimento, usado por critérios clínicos.",
     {"dominio": "sexo_ao_nascer"}),
    ("IDN", "identidade_genero", "nominal", "Identidade de gênero",
     "Gênero com que o participante se identifica hoje, autodeclarado.",
     {"dominio": "identidade_genero", "sensivel": True, "vida_util_dias": 1825}),
    ("IDN", "raca_cor", "nominal", "Raça ou cor autodeclarada",
     "Autodeclaração segundo as cinco categorias do IBGE.",
     {"dominio": "raca_cor", "sensivel": True}),
    ("IDN", "idade_anos", "numerica", "Idade em anos completos",
     "Calculada a partir da data de nascimento, na data da consulta.",
     {"unidade": "anos", "minimo": 0, "maximo": 120, "derivada": True,
      "origem": ["data_nascimento"]}),
    ("IDN", "faixa_etaria", "ordinal", "Faixa etária",
     "Agrupamento da idade em faixas, calculado na consulta.",
     {"dominio": "faixa_etaria", "derivada": True, "origem": ["idade_anos"]}),

    ("LOC", "municipio_residencia", "nominal", "Município onde mora atualmente",
     "Município de residência no momento da coleta, pela tabela do IBGE.",
     {"tabela_referencia": "ibge_municipio", "vida_util_dias": 730}),
    ("LOC", "zona_residencia", "nominal", "Zona do endereço de residência",
     "Se o endereço de moradia fica em área urbana ou rural.",
     {"dominio": "zona_residencia", "vida_util_dias": 730}),
    ("LOC", "tempo_residencia_municipio", "numerica", "Tempo de residência no município, em anos",
     "Há quantos anos o participante mora no município atual.",
     {"unidade": "anos", "minimo": 0, "maximo": 120, "vida_util_dias": 365}),
    ("LOC", "uf_residencia", "nominal", "Unidade federativa de residência",
     "Derivada do município informado, pela tabela do IBGE.",
     {"tabela_referencia": "ibge_uf", "derivada": True, "origem": ["municipio_residencia"]}),

    ("DOM", "escolaridade", "ordinal", "Escolaridade concluída",
     "Nível de ensino mais alto que o participante concluiu.",
     {"dominio": "escolaridade", "vida_util_dias": 1825}),
    ("DOM", "situacao_ocupacional", "nominal", "Situação ocupacional atual",
     "Vínculo de trabalho do participante no momento da coleta.",
     {"dominio": "situacao_ocupacional", "vida_util_dias": 365}),
    ("DOM", "ocupacao", "nominal", "Ocupação exercida",
     "Ocupação principal, pela Classificação Brasileira de Ocupações.",
     {"tabela_referencia": "cbo", "vida_util_dias": 730}),
    ("DOM", "renda_familiar_mensal", "numerica", "Renda familiar mensal",
     "Soma da renda de todos os moradores do domicílio no mês de referência.",
     {"unidade": "reais", "minimo": 0, "maximo": 100000, "vida_util_dias": 365}),
    ("DOM", "beneficio_social", "nominal", "Benefício social recebido atualmente",
     "Programa de transferência ou benefício que o participante recebe hoje.",
     {"dominio": "beneficio_social", "vida_util_dias": 365}),
    ("DOM", "posse_domicilio", "nominal", "Situação de posse do domicílio",
     "Relação com o imóvel onde mora: próprio, alugado ou cedido.",
     {"dominio": "posse_domicilio", "vida_util_dias": 730}),
    ("DOM", "renda_per_capita", "numerica", "Renda per capita",
     "Renda familiar do mês dividida pelo número de moradores do domicílio.",
     {"unidade": "reais", "minimo": 0, "maximo": 100000, "derivada": True,
      "origem": ["renda_familiar_mensal", "pessoas_no_domicilio"]}),

    ("FAM", "estado_civil", "nominal", "Estado civil declarado",
     "Situação conjugal informada pelo participante.",
     {"dominio": "estado_civil", "vida_util_dias": 730}),
    ("FAM", "pessoas_no_domicilio", "numerica", "Pessoas que moram no domicílio",
     "Total de moradores, incluindo o participante.",
     {"unidade": "pessoas", "minimo": 1, "maximo": 30, "vida_util_dias": 365}),
    ("FAM", "menores_no_domicilio", "numerica", "Moradores com menos de 18 anos",
     "Quantos dos moradores do domicílio são menores de idade.",
     {"unidade": "pessoas", "minimo": 0, "maximo": 20, "vida_util_dias": 365}),
    ("FAM", "responsavel_pelo_domicilio", "booleana", "É responsável pelo domicílio",
     "Se o participante é quem responde pelo domicílio.",
     {"vida_util_dias": 730}),
    ("FAM", "cuidador_de_dependente", "booleana", "É cuidador de pessoa dependente",
     "Se cuida de alguém que depende dele para atividades do dia a dia.",
     {"vida_util_dias": 365}),
]

# LIKE '%termo%' não usa índice comum, nem no PostgreSQL. O índice GIN de
# trigramas resolve busca parcial, e por isso a extensão pg_trgm entra junto.
# Em SQLite as duas instruções não existem, então o passo é pulado e a busca
# continua funcionando por varredura, que basta no volume atual.
CRIAR_INDICE = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS catalogo_variavel_busca_trgm "
    "ON catalogo_variavel USING gin (busca gin_trgm_ops)",
]

REMOVER_INDICE = ["DROP INDEX IF EXISTS catalogo_variavel_busca_trgm"]


def carregar(apps, schema_editor):
    Categoria = apps.get_model("catalogo", "Categoria")
    Subcategoria = apps.get_model("catalogo", "Subcategoria")
    Dominio = apps.get_model("catalogo", "Dominio")
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    Variavel = apps.get_model("catalogo", "Variavel")

    dominios = {}
    for codigo, nome, ordinal, opcoes in DOMINIOS:
        dominio = Dominio.objects.create(codigo=codigo, nome=nome, ordinal=ordinal)
        dominios[codigo] = dominio
        for posicao, (valor, rotulo) in enumerate(opcoes, start=1):
            OpcaoDominio.objects.create(dominio=dominio, valor=valor, rotulo=rotulo, ordem=posicao)

    soc = Categoria.objects.create(codigo="SOC", nome="Perfil sociodemográfico", ordem=1)
    subs = {
        codigo: Subcategoria.objects.create(categoria=soc, codigo=codigo, nome=nome, ordem=ordem)
        for codigo, nome, ordem in SUBCATEGORIAS
    }

    # O modelo histórico não tem o save() que preenche a busca, então ela é
    # calculada aqui com a mesma regra do modelo atual.
    criadas = {}
    for sub, codigo, tipo, nome, definicao, extras in VARIAVEIS:
        campos = dict(extras)
        campos.pop("origem", None)
        if "dominio" in campos:
            campos["dominio"] = dominios[campos["dominio"]]
        criadas[codigo] = Variavel.objects.create(
            subcategoria=subs[sub],
            codigo=codigo,
            nome=nome,
            definicao=definicao,
            tipo=tipo,
            busca=VariavelAtual.texto_de_busca(nome, codigo),
            **campos,
        )

    for _, codigo, _, _, _, extras in VARIAVEIS:
        origens = extras.get("origem")
        if origens:
            criadas[codigo].origem.set([criadas[nome] for nome in origens])


def remover(apps, schema_editor):
    for modelo in ("Variavel", "Subcategoria", "Categoria", "OpcaoDominio", "Dominio"):
        apps.get_model("catalogo", modelo).objects.all().delete()


def criar_indice(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for comando in CRIAR_INDICE:
        schema_editor.execute(comando)


def remover_indice(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for comando in REMOVER_INDICE:
        schema_editor.execute(comando)


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0001_initial")]

    operations = [
        migrations.RunPython(carregar, remover),
        migrations.RunPython(criar_indice, remover_indice),
    ]
