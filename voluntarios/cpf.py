import hashlib
import hmac

from cryptography.fernet import Fernet
from django.conf import settings


def normalizar(texto):
    return "".join(c for c in texto if c.isdigit())


def _digito(numeros, peso_inicial):
    soma = sum(int(n) * p for n, p in zip(numeros, range(peso_inicial, 1, -1)))
    resto = soma * 10 % 11
    return 0 if resto == 10 else resto


def valido(cpf):
    # Sequência de dígitos iguais passa na conta dos verificadores, mas não é CPF emitido.
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    return int(cpf[9]) == _digito(cpf[:9], 10) and int(cpf[10]) == _digito(cpf[:10], 11)


def codigo(cpf):
    # Chave única do sistema, porque salt por registro quebraria o determinismo da busca.
    return hmac.new(settings.CHAVE_HMAC.encode(), cpf.encode(), hashlib.sha256).hexdigest()


def cifrar(cpf):
    return Fernet(settings.CHAVE_CIFRA.encode()).encrypt(cpf.encode()).decode()


def decifrar(cifrado):
    return Fernet(settings.CHAVE_CIFRA.encode()).decrypt(cifrado.encode()).decode()


def mascarar(cpf):
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"
