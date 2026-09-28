from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auditoria"
    verbose_name = "auditoria"

    def ready(self):
        from . import sinais  # noqa: F401
