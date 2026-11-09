from django.db import connection, transaction
from django.utils import timezone

from catalogo.models import Variavel

from .models import Participacao, ValorColetado, ValorSensivel


class _Reprovado(Exception):
    def __init__(self, criterio_id):
        self.criterio_id = criterio_id


def variaveis_da_coleta(estudo):
    """Variáveis que o profissional responde, na ordem de pergunta: sensíveis por último.

    Variável derivada não é perguntada, então entram no lugar dela as variáveis de que ela é calculada.
    """
    pendentes = [c.variavel for c in estudo.criterios.select_related("variavel")]
    perguntadas = {}
    while pendentes:
        variavel = pendentes.pop()
        if variavel.derivada:
            pendentes.extend(variavel.origem.all())
        else:
            perguntadas[variavel.id] = variavel
    return sorted(perguntadas.values(), key=lambda v: (v.sensivel, v.subcategoria_id, v.codigo))


def proxima_variavel(participacao):
    respondidas = set(ValorColetado.objects.filter(participacao=participacao).values_list("variavel_id", flat=True))
    respondidas |= set(ValorSensivel.objects.filter(participacao=participacao).values_list("variavel_id", flat=True))
    for variavel in variaveis_da_coleta(participacao.estudo):
        if variavel.id not in respondidas:
            return variavel
    return None


def _criterio_reprovado(participacao):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT criterio_id FROM voluntarios_avaliacao_criterio "
            "WHERE participacao_id = %s AND NOT cumpre ORDER BY criterio_id LIMIT 1",
            [participacao.id],
        )
        linha = cursor.fetchone()
    return linha[0] if linha else None


def registrar_resposta(participacao, variavel, valores, fonte, usuario):
    """Grava a resposta e confere todos os critérios do estudo. Devolve True se o voluntário continua elegível.

    A conferência roda dentro da gravação. Se algum critério reprova, a gravação é desfeita e só a participação
    guarda o motivo. Comum e sensível seguem o mesmo caminho, para a resposta ao profissional não diferir.
    """
    modelo = ValorSensivel if variavel.sensivel else ValorColetado
    try:
        with transaction.atomic():
            modelo.objects.create(
                codigo_voluntario=participacao.voluntario.codigo_hmac,
                variavel=variavel,
                fonte=fonte,
                participacao=participacao,
                coletado_por=usuario,
                **valores,
            )
            reprovado = _criterio_reprovado(participacao)
            if reprovado:
                raise _Reprovado(reprovado)
    except _Reprovado as erro:
        participacao.situacao = Participacao.Situacao.ELIMINADA
        participacao.criterio_reprovado_id = erro.criterio_id
        participacao.encerrada_em = timezone.now()
        participacao.save(update_fields=["situacao", "criterio_reprovado", "encerrada_em"])
        return False
    return True


def concluir_se_terminou(participacao):
    if participacao.situacao == Participacao.Situacao.EM_COLETA and proxima_variavel(participacao) is None:
        participacao.situacao = Participacao.Situacao.CONCLUIDA
        participacao.encerrada_em = timezone.now()
        participacao.save(update_fields=["situacao", "encerrada_em"])
