import logging
from datetime import date
from decimal import Decimal

from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Participacao, ValorColetado, ValorSensivel
from .pendencias import variaveis_faltantes

logger = logging.getLogger(__name__)


class _Desfazer(Exception):
    """Desfaz a transação de conferência. Nada da coleta chega a ser gravado."""

    def __init__(self, criterio_id=None):
        self.criterio_id = criterio_id


def variaveis_da_coleta(participacao):
    """Variáveis que o profissional ainda precisa responder: as que faltam para avaliar os critérios do estudo.

    O voluntário que já tem valor válido de um estudo anterior não responde de novo, e a variável derivada
    entra pelas origens. Sensíveis ficam por último. O banco não muda durante a coleta, então a lista é estável.
    """
    return variaveis_faltantes(participacao.voluntario_id, participacao.estudo_id)


def chave_da_sessao(participacao):
    return f"coleta_{participacao.id}"


def respostas_pendentes(sessao, participacao):
    """Respostas já aceitas pela conferência e ainda não gravadas, guardadas na sessão do profissional."""
    return dict(sessao.get(chave_da_sessao(participacao), {}))


def proxima_variavel(participacao, pendentes):
    for variavel in variaveis_da_coleta(participacao):
        if str(variavel.id) not in pendentes:
            return variavel
    return None


def _serializar(valores, fonte):
    campos = {}
    for nome, valor in valores.items():
        if nome == "opcao":
            campos["opcao_id"] = valor.id
        elif isinstance(valor, date):
            campos[nome] = valor.isoformat()
        else:
            campos[nome] = str(valor) if isinstance(valor, Decimal) else valor
    return {"valores": campos, "fonte": fonte}


def _valores_do_modelo(campos):
    valores = dict(campos)
    if "valor_numero" in valores:
        valores["valor_numero"] = Decimal(valores["valor_numero"])
    if "valor_data" in valores:
        valores["valor_data"] = date.fromisoformat(valores["valor_data"])
    return valores


def _criterio_reprovado(participacao):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT criterio_id FROM voluntarios_avaliacao_criterio "
            "WHERE participacao_id = %s AND NOT cumpre ORDER BY criterio_id LIMIT 1",
            [participacao.id],
        )
        linha = cursor.fetchone()
    return linha[0] if linha else None


def registrar_resposta(participacao, variavel, valores, fonte, usuario, sessao):
    """Confere a resposta com as anteriores e devolve "continua", "concluida" ou "eliminada".

    RN24: nada é gravado até que todos os critérios estejam atendidos. A conferência insere as respostas dentro de
    uma transação para a view SQL compará-las com os critérios e sempre desfaz, salvo na última resposta. Reprovou
    em qualquer ponto, a coleta acaba sem gravar nenhum valor, nem os anteriores. Comum e sensível seguem o mesmo
    caminho, para a resposta ao profissional não diferir.
    """
    chave = chave_da_sessao(participacao)
    respostas = respostas_pendentes(sessao, participacao)
    respostas[str(variavel.id)] = _serializar(valores, fonte)
    perguntadas = variaveis_da_coleta(participacao)
    sensiveis = {str(v.id) for v in perguntadas if v.sensivel}
    completa = all(str(v.id) in respostas for v in perguntadas)
    try:
        with transaction.atomic():
            for variavel_id, resposta in respostas.items():
                modelo = ValorSensivel if variavel_id in sensiveis else ValorColetado
                modelo.objects.create(
                    codigo_voluntario=participacao.voluntario.codigo_hmac,
                    variavel_id=int(variavel_id),
                    fonte=resposta["fonte"],
                    participacao=participacao,
                    coletado_por=usuario,
                    **_valores_do_modelo(resposta["valores"]),
                )
            reprovado = _criterio_reprovado(participacao)
            if reprovado or not completa:
                raise _Desfazer(reprovado)
    except _Desfazer as erro:
        if erro.criterio_id:
            sessao.pop(chave, None)
            participacao.situacao = Participacao.Situacao.ELIMINADA
            participacao.criterio_reprovado_id = erro.criterio_id
            participacao.encerrada_em = timezone.now()
            participacao.save(update_fields=["situacao", "criterio_reprovado", "encerrada_em"])
            return "eliminada"
        sessao[chave] = respostas
        return "continua"
    sessao.pop(chave, None)
    concluir(participacao)
    return "concluida"


def concluir(participacao):
    participacao.situacao = Participacao.Situacao.CONCLUIDA
    participacao.encerrada_em = timezone.now()
    participacao.save(update_fields=["situacao", "encerrada_em"])
    notificar_pesquisador(participacao)


def concluir_se_nao_ha_o_que_perguntar(participacao):
    if participacao.situacao == Participacao.Situacao.EM_COLETA and not variaveis_da_coleta(participacao):
        concluir(participacao)


def notificar_pesquisador(participacao):
    """RF09 CA02. O email leva só o estudo e o código curto, nunca o CPF nem os valores coletados."""
    estudo = participacao.estudo
    contexto = {
        "pesquisador": estudo.pesquisador,
        "estudo": estudo,
        "codigo": participacao.voluntario.codigo_hmac[:8],
    }
    mensagem = EmailMultiAlternatives(
        f"Coleta concluída no estudo {estudo.nome}",
        render_to_string("voluntarios/coleta_concluida_email.txt", contexto),
        to=[estudo.pesquisador.email],
    )
    try:
        mensagem.send()
    except Exception:
        # A coleta já foi gravada, então a falha do envio não a desfaz.
        logger.exception("Falha ao notificar o pesquisador da coleta concluída.")
