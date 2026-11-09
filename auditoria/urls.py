from django.urls import path

from .views import listar

app_name = "auditoria"

urlpatterns = [
    path("", listar, name="listar"),
]
