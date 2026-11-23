from django.core.management.base import BaseCommand
from django.utils import timezone

from estudos.models import Estudo
from voluntarios import eliminacao


class Command(BaseCommand):
    help = "Elimina os dados dos estudos encerrados cujo prazo de guarda (RN33) terminou."

    def handle(self, *args, **opcoes):
        vencidos = Estudo.objects.filter(situacao=Estudo.Situacao.ENCERRADO, prazo_guarda_ate__lte=timezone.localdate())
        for estudo in vencidos:
            # Estudo sem voluntário a eliminar fica de fora para a rotina diária não repetir o registro de auditoria.
            if eliminacao.separar(estudo)[0].exists():
                eliminacao.eliminar_dados(estudo)
