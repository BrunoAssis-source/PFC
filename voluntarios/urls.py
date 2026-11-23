from django.urls import path

from .views import cadastrar, coletar, detalhe, identificar, opcoes_filhas, tcle_do_estudo, vincular
from .views_candidatos import candidatos, exportar, incluir, recusar

app_name = "voluntarios"

urlpatterns = [
    path("", identificar, name="identificar"),
    path("cadastrar/", cadastrar, name="cadastrar"),
    path("estudos/<int:id>/candidatos/", candidatos, name="candidatos"),
    path("estudos/<int:id>/candidatos/incluir/", incluir, name="incluir_candidatos"),
    path("estudos/<int:id>/candidatos/recusar/", recusar, name="recusar_candidatos"),
    path("estudos/<int:id>/tcle/", tcle_do_estudo, name="tcle_do_estudo"),
    path("estudos/<int:id>/exportar/", exportar, name="exportar"),
    path("<int:id>/", detalhe, name="detalhe"),
    path("<int:id>/vincular/", vincular, name="vincular"),
    path("<int:id>/participacoes/<int:participacao_id>/coleta/", coletar, name="coleta"),
    path("<int:id>/participacoes/<int:participacao_id>/coleta/opcoes/", opcoes_filhas, name="opcoes_filhas"),
]
