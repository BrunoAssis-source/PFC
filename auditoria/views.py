from django.core.paginator import Paginator
from django.shortcuts import render

from autenticacao.permissoes import exige_administrador

from .models import RegistroAuditoria


@exige_administrador
def listar(request):
    registros = RegistroAuditoria.objects.select_related("usuario")
    pagina = Paginator(registros, 50).get_page(request.GET.get("pagina"))
    return render(request, "auditoria/lista.html", {"pagina": pagina})
