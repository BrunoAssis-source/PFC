from django.urls import path

from .views import (
    criar,
    criar_criterio,
    detalhe,
    editar,
    escolher_variavel,
    lista_variaveis,
    listar,
    propor_variavel,
    remover_criterio,
)

app_name = "estudos"

urlpatterns = [
    path("", listar, name="listar"),
    path("novo/", criar, name="criar"),
    path("<int:id>/", detalhe, name="detalhe"),
    path("<int:id>/editar/", editar, name="editar"),
    path("<int:id>/criterios/novo/", escolher_variavel, name="escolher_variavel"),
    path("<int:id>/criterios/variaveis/", lista_variaveis, name="lista_variaveis"),
    path("<int:id>/criterios/propor/", propor_variavel, name="propor_variavel"),
    path("<int:id>/criterios/novo/<int:variavel_id>/", criar_criterio, name="criar_criterio"),
    path("<int:id>/criterios/<int:criterio_id>/remover/", remover_criterio, name="remover_criterio"),
]
