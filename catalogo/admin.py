from django.contrib import admin

from .models import Categoria, Dominio, OpcaoDominio, SinonimoVariavel, Subcategoria, Variavel


class SubcategoriaInline(admin.TabularInline):
    model = Subcategoria
    extra = 0


class OpcaoInline(admin.TabularInline):
    model = OpcaoDominio
    extra = 0


class SinonimoInline(admin.TabularInline):
    model = SinonimoVariavel
    extra = 1


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "ordem")
    inlines = [SubcategoriaInline]


@admin.register(Dominio)
class DominioAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "ordinal")

    def get_inlines(self, request, obj=None):
        # O domínio de municípios tem milhares de opções, e uma linha editável
        # para cada uma travaria a página.
        return [] if obj and obj.superior_id else [OpcaoInline]


@admin.register(Variavel)
class VariavelAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "subcategoria", "tipo", "vida_util_dias", "derivada", "sensivel")
    list_filter = ("tipo", "derivada", "sensivel", "subcategoria__categoria")
    search_fields = ("codigo", "nome")
    filter_horizontal = ("origem",)
    inlines = [SinonimoInline]
