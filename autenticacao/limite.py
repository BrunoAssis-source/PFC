from django.core.cache import cache

# Por email, não por IP: o IP vem de cabeçalho que o cliente pode forjar. O custo é que alguém pode travar o login
# de outra pessoa por 15 minutos; o bloqueio expira sozinho e não desativa a conta.
JANELA = 15 * 60
LOGIN_MAXIMO = 5
RESET_MAXIMO = 3
RESET_JANELA = 60 * 60


def _chave(tipo, email):
    return f"limite:{tipo}:{email.strip().lower()}"


def bloqueado(tipo, email, maximo):
    # Email vazio ou inválido não tem chave própria; senão todos eles dividiriam o mesmo contador.
    return bool(email) and cache.get(_chave(tipo, email), 0) >= maximo


def registrar_falha(tipo, email, janela=JANELA):
    if not email:
        return
    chave = _chave(tipo, email)
    # add cria com prazo; incr depois não renova o prazo, então a janela não se estende a cada tentativa.
    cache.add(chave, 0, janela)
    try:
        cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, janela)


def limpar(tipo, email):
    cache.delete(_chave(tipo, email))
