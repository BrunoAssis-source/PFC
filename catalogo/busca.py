from django.contrib.postgres.lookups import Unaccent
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Exists, F, Q, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce, Greatest

from .models import SinonimoVariavel, Variavel

LIMIAR_SIMILARIDADE = 0.4

# A faixa etária existe só como derivada da idade e não serve de critério.
OCULTAS_NO_SELETOR = ("faixa_etaria",)


def selecionaveis():
    # Categórica só entra com domínio. As que dependem de tabela de referência
    # ficam fora, e texto livre nunca serve de critério.
    return (
        Variavel.objects.exclude(tipo=Variavel.Tipo.TEXTO)
        .exclude(codigo__in=OCULTAS_NO_SELETOR)
        .filter(Q(dominio__isnull=False) | Q(tipo__in=["numerica", "data", "booleana"]))
        .select_related("subcategoria", "subcategoria__categoria")
    )


def buscar_criterios(termo):
    """Variáveis selecionáveis cujo nome, nome curto ou sinônimo combina com o termo.

    Ignora acento e caixa. O contém cobre termo curto, que o trigram pontua
    baixo mesmo quando acerta. A similaridade trigram cobre erro de digitação
    ("escolaridde"). O resultado vem do mais parecido para o menos.
    """
    termo = termo.strip()
    if not termo:
        return Variavel.objects.none()

    alvo = Unaccent(Value(termo))
    sinonimos = SinonimoVariavel.objects.filter(variavel=OuterRef("pk"))
    melhor_sinonimo = (
        sinonimos.annotate(s=TrigramSimilarity(Unaccent("termo"), alvo))
        .order_by("-s")
        .values("s")[:1]
    )
    return (
        selecionaveis()
        .annotate(
            achou_sinonimo=Exists(sinonimos.filter(termo__unaccent__icontains=termo)),
            similaridade=Greatest(
                TrigramSimilarity(Unaccent("nome"), alvo),
                TrigramSimilarity(Unaccent("nome_curto"), alvo),
                Coalesce(Subquery(melhor_sinonimo), 0.0),
            ),
        )
        .filter(
            Q(nome__unaccent__icontains=termo)
            | Q(nome_curto__unaccent__icontains=termo)
            | Q(achou_sinonimo=True)
            | Q(similaridade__gte=LIMIAR_SIMILARIDADE)
        )
        .order_by(F("similaridade").desc(), "nome")
    )
