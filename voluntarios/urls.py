from django.urls import path

from .views import cadastrar, detalhe, identificar, vincular

app_name = "voluntarios"

urlpatterns = [
    path("", identificar, name="identificar"),
    path("cadastrar/", cadastrar, name="cadastrar"),
    path("<int:id>/", detalhe, name="detalhe"),
    path("<int:id>/vincular/", vincular, name="vincular"),
]
