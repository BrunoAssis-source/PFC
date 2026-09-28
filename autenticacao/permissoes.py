from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from auditoria.models import RegistroAuditoria
from auditoria.servicos import registrar


def exige_perfil(*perfis):
    def decorador(view):
        @wraps(view)
        @login_required
        def verificar(request, *args, **kwargs):
            if request.user.perfil not in perfis:
                registrar(
                    RegistroAuditoria.Acao.ACESSO_NEGADO,
                    request=request,
                    usuario=request.user,
                    objeto=request.path,
                )
                raise PermissionDenied("Seu perfil não tem acesso a esta tela.")
            return view(request, *args, **kwargs)

        return verificar

    return decorador


def exige_administrador(view):
    # Administrador é quem tem is_staff, do jeito que o Django admin já define. Não é um perfil de pesquisa.
    @wraps(view)
    @login_required
    def verificar(request, *args, **kwargs):
        if not request.user.is_staff:
            registrar(
                RegistroAuditoria.Acao.ACESSO_NEGADO,
                request=request,
                usuario=request.user,
                objeto=request.path,
            )
            raise PermissionDenied("Apenas administradores acessam esta tela.")
        return view(request, *args, **kwargs)

    return verificar
