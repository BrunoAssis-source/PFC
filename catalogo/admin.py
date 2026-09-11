from django.contrib import admin

from .models import Categoria, Dominio, OpcaoDominio, Subcategoria, Variavel


class SubcategoriaInline(admin.TabularInline):
    model = Subcategoria
    extra = 0


class OpcaoInline(admin.TabularInline):
    model = OpcaoDominio
    extra = 0


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "ordem")
    inlines = [SubcategoriaInline]


@admin.register(Dominio)
class DominioAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "ordinal")
    inlines = [OpcaoInline]


@admin.register(Variavel)
class VariavelAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "subcategoria", "tipo", "vida_util_dias", "derivada", "sensivel")
    list_filter = ("tipo", "derivada", "sensivel", "subcategoria__categoria")
    search_fields = ("codigo", "nome")
    filter_horizontal = ("origem",)
