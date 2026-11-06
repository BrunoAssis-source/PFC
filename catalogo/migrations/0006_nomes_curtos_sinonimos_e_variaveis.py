from django.db import migrations

from catalogo.models import Variavel as VariavelAtual

# codigo da variável: (nome curto, sinônimos que o pesquisador costuma digitar)
ROTULOS = {
    "data_nascimento": ("Data de nascimento", ["nascimento", "aniversário"]),
    "sexo_ao_nascer": ("Sexo ao nascer", ["sexo", "sexo biológico", "masculino", "feminino"]),
    "identidade_genero": ("Identidade de gênero", ["gênero", "transgênero", "cis"]),
    "raca_cor": ("Raça ou cor", ["raça", "cor", "etnia"]),
    "idade_anos": ("Idade", ["anos", "idade"]),
    "faixa_etaria": ("Faixa etária", ["faixa de idade"]),
    "municipio_residencia": ("Município", ["cidade", "onde mora"]),
    "zona_residencia": ("Zona de residência", ["zona rural", "zona urbana", "rural", "urbana"]),
    "tempo_residencia_municipio": ("Tempo de residência", ["tempo na cidade", "anos morando"]),
    "uf_residencia": ("Estado (UF)", ["estado", "uf"]),
    "escolaridade": ("Escolaridade", ["grau de instrução", "nível de ensino", "estudo", "formação"]),
    "situacao_ocupacional": ("Situação ocupacional", ["trabalho", "emprego", "empregado", "desempregado"]),
    "ocupacao": ("Ocupação", ["profissão", "cargo"]),
    "renda_familiar_mensal": ("Renda familiar", ["renda", "salário", "rendimento"]),
    "beneficio_social": ("Benefício social", ["bolsa família", "auxílio", "bpc"]),
    "posse_domicilio": ("Posse da moradia", ["casa própria", "aluguel", "moradia"]),
    "renda_per_capita": ("Renda per capita", ["renda por pessoa"]),
    "estado_civil": ("Estado civil", ["casado", "solteiro", "união estável", "viúvo"]),
    "pessoas_no_domicilio": ("Moradores do domicílio", ["pessoas na casa", "tamanho da família", "moradores"]),
    "menores_no_domicilio": ("Menores de idade em casa", ["crianças", "filhos menores", "menores"]),
    "responsavel_pelo_domicilio": ("Responsável pelo domicílio", ["chefe de família", "chefe do domicílio"]),
    "cuidador_de_dependente": ("Cuidador de dependente", ["cuidador", "cuida de alguém"]),
    "orientacao_sexual": ("Orientação sexual", ["heterossexual", "homossexual", "bissexual", "lgbt"]),
    "numero_filhos": ("Número de filhos", ["filhos", "quantos filhos"]),
}

DOMINIO_NOVO = ("orientacao_sexual", "Orientação sexual", [
    ("heterossexual", "Heterossexual"), ("homossexual", "Homossexual"),
    ("bissexual", "Bissexual"), ("outra", "Outra"), ("nao_responder", "Prefiro não responder"),
])

# (subcategoria, codigo, tipo, nome, definição, campos extras)
VARIAVEIS_NOVAS = [
    ("IDN", "orientacao_sexual", "nominal", "Orientação sexual autodeclarada",
     "Orientação sexual com que o participante se identifica, autodeclarada.",
     {"dominio": "orientacao_sexual", "sensivel": True, "vida_util_dias": 1825}),
    ("FAM", "numero_filhos", "numerica", "Número de filhos",
     "Quantidade de filhos do participante, biológicos ou adotivos.",
     {"unidade": "filhos", "minimo": 0, "maximo": 20, "vida_util_dias": 365}),
]


def aplicar(apps, schema_editor):
    Dominio = apps.get_model("catalogo", "Dominio")
    OpcaoDominio = apps.get_model("catalogo", "OpcaoDominio")
    Subcategoria = apps.get_model("catalogo", "Subcategoria")
    Variavel = apps.get_model("catalogo", "Variavel")
    Sinonimo = apps.get_model("catalogo", "SinonimoVariavel")

    codigo, nome, opcoes = DOMINIO_NOVO
    dominio = Dominio.objects.create(codigo=codigo, nome=nome, ordinal=False)
    for posicao, (valor, rotulo) in enumerate(opcoes, start=1):
        OpcaoDominio.objects.create(dominio=dominio, valor=valor, rotulo=rotulo, ordem=posicao)

    for sub, codigo, tipo, nome, definicao, extras in VARIAVEIS_NOVAS:
        campos = dict(extras)
        if "dominio" in campos:
            campos["dominio"] = Dominio.objects.get(codigo=campos["dominio"])
        Variavel.objects.create(
            subcategoria=Subcategoria.objects.get(categoria__codigo="SOC", codigo=sub),
            codigo=codigo,
            nome=nome,
            definicao=definicao,
            tipo=tipo,
            busca=VariavelAtual.texto_de_busca(nome, codigo),
            **campos,
        )

    for codigo, (nome_curto, sinonimos) in ROTULOS.items():
        variavel = Variavel.objects.get(codigo=codigo)
        variavel.nome_curto = nome_curto
        variavel.save(update_fields=["nome_curto"])
        for termo in sinonimos:
            Sinonimo.objects.create(variavel=variavel, termo=termo)


def desfazer(apps, schema_editor):
    apps.get_model("catalogo", "SinonimoVariavel").objects.all().delete()
    apps.get_model("catalogo", "Variavel").objects.filter(
        codigo__in=[v[1] for v in VARIAVEIS_NOVAS]
    ).delete()
    apps.get_model("catalogo", "Dominio").objects.filter(codigo=DOMINIO_NOVO[0]).delete()


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0005_nome_curto_e_sinonimos")]

    operations = [migrations.RunPython(aplicar, desfazer)]
