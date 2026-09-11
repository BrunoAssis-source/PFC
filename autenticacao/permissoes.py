from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def exige_perfil(*perfis):
    def decorador(view):
        @wraps(view)
        @login_required
        def verificar(request, *args, **kwargs):
            if request.user.perfil not in perfis:
                raise PermissionDenied("Seu perfil não tem acesso a esta tela.")
            return view(request, *args, **kwargs)

        return verificar

    return decorador
