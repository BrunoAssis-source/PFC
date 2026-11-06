from django.urls import path

from .views import (
    adicionar_criterio,
    buscar_variaveis,
    configurar_criterio,
    criar,
    criterios,
    detalhe,
    editar,
    listar,
    previa_criterio,
    propor_variavel,
    remover_criterio,
)

app_name = "estudos"

urlpatterns = [
    path("", listar, name="listar"),
    path("novo/", criar, name="criar"),
    path("<int:id>/", detalhe, name="detalhe"),
    path("<int:id>/editar/", editar, name="editar"),
    path("<int:id>/criterios/", criterios, name="criterios"),
    path("<int:id>/criterios/busca/", buscar_variaveis, name="buscar_variaveis"),
    path("<int:id>/criterios/propor/", propor_variavel, name="propor_variavel"),
    path("<int:id>/criterios/variavel/<int:variavel_id>/", configurar_criterio, name="configurar_criterio"),
    path("<int:id>/criterios/variavel/<int:variavel_id>/previa/", previa_criterio, name="previa_criterio"),
    path("<int:id>/criterios/variavel/<int:variavel_id>/adicionar/", adicionar_criterio, name="adicionar_criterio"),
    path("<int:id>/criterios/<int:criterio_id>/remover/", remover_criterio, name="remover_criterio"),
]
