from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "acao", "usuario", "email_tentativa", "objeto", "ip")
    list_filter = ("acao",)
    search_fields = ("usuario__email", "email_tentativa", "objeto")
    date_hierarchy = "criado_em"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
