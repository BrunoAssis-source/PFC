from django.contrib.postgres.lookups import Unaccent
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, Value

from .models import Variavel

LIMIAR_SIMILARIDADE = 0.3


def buscar_criterios(termo):
    """Variáveis cujo nome contém o termo, ignorando acento e caixa, ou se parece com ele.

    A similaridade trigram cobre erro de digitação ("escolaridde"). O contém
    cobre termo curto, que o trigram pontua baixo mesmo quando acerta.
    """
    termo = termo.strip()
    if not termo:
        return Variavel.objects.none()
    return (
        Variavel.objects.annotate(
            similaridade=TrigramSimilarity(Unaccent("nome"), Unaccent(Value(termo)))
        )
        .filter(Q(nome__unaccent__icontains=termo) | Q(similaridade__gte=LIMIAR_SIMILARIDADE))
        .order_by("-similaridade", "nome")
    )
