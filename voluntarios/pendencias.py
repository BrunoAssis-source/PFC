from django.db import connection

from catalogo.models import Variavel
from estudos.models import Estudo

from .models import Voluntario


def _consultar(sql, parametros=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parametros)
        return cursor.fetchall()


def classificacao(voluntario_id=None, estudo_id=None):
    """RN26 pela view voluntarios_classificacao. Devolve {(voluntario_id, estudo_id): classe} dos estudos ativos."""
    linhas = _consultar(
        "SELECT voluntario_id, estudo_id, classe FROM voluntarios_classificacao "
        "WHERE (%s IS NULL OR voluntario_id = %s) AND (%s IS NULL OR estudo_id = %s)",
        [voluntario_id, voluntario_id, estudo_id, estudo_id],
    )
    return {(voluntario, estudo): classe for voluntario, estudo, classe in linhas}


def variaveis_faltantes(voluntario_id, estudo_id):
    """Variáveis sem valor válido que impedem avaliar todos os critérios do estudo, na ordem em que se perguntam."""
    ids = [
        linha[0]
        for linha in _consultar(
            "SELECT variavel_id FROM voluntarios_faltantes WHERE voluntario_id = %s AND estudo_id = %s",
            [voluntario_id, estudo_id],
        )
    ]
    # Sensíveis por último, para quem seria eliminado não responder pergunta sensível à toa.
    return sorted(Variavel.objects.filter(id__in=ids), key=lambda v: (v.sensivel, v.subcategoria_id, v.codigo))


def pendentes(estudo_id=None, voluntario_id=None):
    """Pares pendentes de voluntários que já têm dados na base, com só as variáveis que faltam coletar.

    Não carrega critério, valor nem classificação: a tela do profissional não os mostra (RN25 e RN28).
    """
    pares = _consultar(
        "SELECT voluntario_id, estudo_id FROM voluntarios_classificacao "
        "WHERE classe = 'pendente' AND registrado "
        "AND (%s IS NULL OR estudo_id = %s) AND (%s IS NULL OR voluntario_id = %s) "
        "ORDER BY estudo_id, voluntario_id",
        [estudo_id, estudo_id, voluntario_id, voluntario_id],
    )
    voluntarios = Voluntario.objects.in_bulk({v for v, _ in pares})
    estudos = Estudo.objects.in_bulk({e for _, e in pares})
    return [
        {
            "voluntario": voluntarios[v],
            "estudo": estudos[e],
            "codigo": voluntarios[v].codigo_hmac[:8],
            "variaveis": variaveis_faltantes(v, e),
        }
        for v, e in pares
    ]
