from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("estudos/", include("estudos.urls")),
    path("", include("autenticacao.urls")),
]
