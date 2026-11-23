import pytest


@pytest.fixture(autouse=True)
def sem_aceite_dos_termos(settings):
    # Os testes criam usuários direto no banco. Os de aceite ligam a exigência de volta.
    settings.EXIGE_ACEITE_DOS_TERMOS = False
