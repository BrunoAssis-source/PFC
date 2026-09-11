from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    model = Usuario
    ordering = ("email",)
    list_display = ("email", "nome_completo", "perfil", "is_active", "is_staff")
    list_filter = ("perfil", "is_active", "is_staff")
    search_fields = ("email", "nome_completo")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("nome_completo",)}),
        ("Perfil", {"fields": ("perfil",)}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nome_completo", "perfil", "password1", "password2", "is_active", "is_staff")}),
    )
