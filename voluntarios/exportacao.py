import csv

from django.db import connection

from catalogo.models import OpcaoDominio, Variavel, formatar_numero

from .models import DecisaoCandidato

# Ponto e vírgula e BOM porque o Excel em português abre CSV com vírgula numa coluna só e sem BOM troca os acentos.
SEPARADOR = ";"
BOM = "﻿"


def _cabecalho(variavel):
    nome = variavel.nome_curto or variavel.nome
    return f"{nome} ({variavel.unidade})" if variavel.unidade else nome


def _texto(numero, data, opcao, booleano, casas=None):
    if opcao is not None:
        return opcao.rotulo
    if booleano is not None:
        return "Sim" if booleano else "Não"
    if data is not None:
        return data.strftime("%d/%m/%Y")
    if numero is not None:
        return formatar_numero(numero, casas)
    return ""


def _valores_efetivos(codigos, variaveis):
    # variaveis é {id: Variavel}. Valor em reais sai sempre com centavos.
    # Lê da mesma view da verificação. Assim as derivadas (idade, faixa etária, renda per capita) aparecem e o valor
    # vencido pela vida útil sai vazio, igual ao que a classificação enxerga.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT codigo_voluntario, variavel_id, valor_numero, valor_data, opcao_id, valor_booleano "
            "FROM voluntarios_valor_efetivo WHERE codigo_voluntario = ANY(%s) AND variavel_id = ANY(%s)",
            [codigos, list(variaveis)],
        )
        linhas = cursor.fetchall()
    opcoes = OpcaoDominio.objects.in_bulk({l[4] for l in linhas if l[4] is not None})
    return {
        (codigo, variavel): _texto(numero, data, opcoes.get(opcao), booleano, 2 if variaveis[variavel].unidade == "reais" else None)
        for codigo, variavel, numero, data, opcao, booleano in linhas
    }


def tabela(estudo):
    """Cabeçalho e linhas dos voluntários incluídos pelo pesquisador, com o valor efetivo de cada variável dos
    critérios. Identifica só pelo código curto, nunca pelo CPF."""
    ids = estudo.criterios.order_by("id").values_list("variavel_id", flat=True)
    ordem = list(dict.fromkeys(ids))
    variaveis = {v.id: v for v in Variavel.objects.filter(id__in=ordem)}
    decisoes = list(estudo.decisoes.filter(decisao=DecisaoCandidato.Decisao.INCLUIDO).order_by("decidido_em"))
    atuais = _valores_efetivos([d.codigo_voluntario for d in decisoes], variaveis)

    cabecalho = ["Código", "Decisão", "Decidido em"] + [_cabecalho(variaveis[i]) for i in ordem]
    linhas = [
        [d.codigo_voluntario[:8], d.get_decisao_display().capitalize(), d.decidido_em.strftime("%d/%m/%Y %H:%M")]
        + [atuais.get((d.codigo_voluntario, i), "") for i in ordem]
        for d in decisoes
    ]
    return cabecalho, linhas


def escrever_csv(destino, estudo):
    destino.write(BOM)
    escritor = csv.writer(destino, delimiter=SEPARADOR)
    cabecalho, linhas = tabela(estudo)
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
