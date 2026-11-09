from django.urls import path

from .views import cadastrar, coletar, detalhe, identificar, vincular

app_name = "voluntarios"

urlpatterns = [
    path("", identificar, name="identificar"),
    path("cadastrar/", cadastrar, name="cadastrar"),
    path("<int:id>/", detalhe, name="detalhe"),
    path("<int:id>/vincular/", vincular, name="vincular"),
    path("<int:id>/participacoes/<int:participacao_id>/coleta/", coletar, name="coleta"),
]
