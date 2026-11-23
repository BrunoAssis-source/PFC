from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .models import TERMOS_VERSAO

# Telas que a pessoa precisa alcançar sem ter aceitado: o próprio aceite, a saída e os textos que ela vai aceitar.
LIVRES = ("aceitar_termos", "logout", "termos_de_uso", "politica_privacidade")


class ExigeAceiteDosTermos:
    """Leva ao aceite quem está autenticado sem ter aceitado a versão atual dos termos.

    Cobre a conta criada pelo administrador, a anterior ao registro do aceite e a que aceitou uma versão antiga.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        if (
            getattr(settings, "EXIGE_ACEITE_DOS_TERMOS", True)
            and usuario.is_authenticated
            and (usuario.termos_aceitos_em is None or usuario.termos_versao != TERMOS_VERSAO)
            and request.path not in {reverse(nome) for nome in LIVRES}
        ):
            return redirect("aceitar_termos")
        return self.get_response(request)
