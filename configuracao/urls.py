from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("estudos/", include("estudos.urls")),
    path("auditoria/", include("auditoria.urls")),
    path("voluntarios/", include("voluntarios.urls")),
    path("", include("autenticacao.urls")),
]
