from django.contrib import admin

from .models import Criterio, Estudo


@admin.register(Estudo)
class EstudoAdmin(admin.ModelAdmin):
    list_display = ("nome", "condicao", "situacao", "pesquisador", "criado_em")
    list_filter = ("situacao",)
    search_fields = ("nome", "condicao")


@admin.register(Criterio)
class CriterioAdmin(admin.ModelAdmin):
    list_display = ("estudo", "variavel", "operador")
    list_filter = ("operador", "variavel__subcategoria")
