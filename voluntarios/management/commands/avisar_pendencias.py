from django.core.management.base import BaseCommand

from voluntarios.pendencias import sincronizar_notificacoes


class Command(BaseCommand):
    help = "Reavalia as pendências e avisa o profissional das novas, inclusive as que surgem quando um valor vence."

    def handle(self, *args, **opcoes):
        # O vencimento pela vida útil não gera evento no sistema, então só uma rotina periódica o percebe.
        sincronizar_notificacoes()
