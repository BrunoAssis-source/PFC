# UniData

Sistema web para orientar a coleta de dados de voluntários de pesquisa a partir dos critérios de elegibilidade definidos por cada estudo.

O pesquisador cadastra um estudo, as variáveis que ele exige e seus critérios. O profissional registra os dados de cada voluntário e o sistema verifica a compatibilidade durante o preenchimento, interrompendo quando um critério deixa de ser atendido. Os dados já registrados ficam disponíveis para outros estudos enquanto houver pesquisa ativa vinculada ao voluntário.

A classificação produzida pelo sistema é sugestão. A decisão sobre quem entra em um estudo é do pesquisador e fica registrada.

Projeto Final de Curso do Bacharelado em Sistemas de Informação da Universidade de Mogi das Cruzes.

Autores: Bruno de Faria Assis e João Gabriel Dos Santos.

## Estado atual

Estão implementados a autenticação com controle de acesso por perfil, o catálogo de variáveis e o cadastro de estudos e critérios.

A autenticação cobre o cadastro restrito ao domínio `@alunos.umc.br`, login, recuperação de senha por email e a separação entre pesquisador e profissional, com as rotas de cada um negando acesso a quem não tem o perfil.

O pesquisador cadastra e edita estudos, cada um com situação de rascunho, ativo ou encerrado. Em cada estudo ele inclui e remove critérios de elegibilidade. Todo critério parte de uma variável do catálogo, que o pesquisador encontra descendo por categoria e subcategoria ou buscando pelo nome. Se a busca não acha a variável, ele pode propor uma nova, que entra no catálogo e fica disponível para qualquer estudo. O catálogo já vem carregado com as variáveis do perfil sociodemográfico.

Os operadores oferecidos dependem do tipo da variável:

| Tipo | Operadores |
|---|---|
| Numérica | =, ≠, <, ≤, >, ≥, entre |
| Categórica nominal | é, não é, está em, não está em |
| Categórica ordinal | os da nominal, mais ≤, ≥ e entre, pela ordem das opções |
| Booleana | é verdadeiro, é falso |
| Data | antes de, depois de, entre |

Variável de texto livre não serve de critério e não aparece no seletor. Um critério de data pode ser escrito com dia, só com mês e ano ou só com o ano, e é exibido do mesmo jeito que foi informado.

Faltam o cadastro de voluntários, os valores coletados e a verificação de elegibilidade. Por isso as telas do profissional, registro de dados e pendências, existem ainda sem conteúdo. O banco em uso durante o desenvolvimento é SQLite; a migração para PostgreSQL está prevista.

## Stack

Django 5.2 no padrão MVT, PostgreSQL (SQLite por enquanto, no desenvolvimento), Bootstrap 5 e pytest. Aplicação monolítica, sem API própria, porque o único cliente é o navegador.

O envio de email usa a API transacional do Brevo, com requisição HTTP direta em um backend de email do Django.

Em produção: Render para a aplicação e Neon para o banco.

## Como executar

Requer Python 3.14.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copie o `.env.example` para `.env` e preencha as variáveis descritas abaixo. Depois:

```
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver
```

O `createsuperuser` pede email antes do nome, porque o email é o campo de identificação do usuário no lugar do nome de acesso padrão do Django.

A aplicação responde em http://127.0.0.1:8000. A raiz é a tela de login, e o admin do Django fica em `/admin/`. A política de privacidade, em `/politica-de-privacidade/`, abre sem login.

## Variáveis de ambiente

Ficam no arquivo `.env`, na raiz, que não é versionado. O `settings.py` lê esse arquivo na subida; variável já definida no ambiente tem precedência sobre o que estiver escrito nele.

| Variável | Uso |
|---|---|
| `DJANGO_SECRET_KEY` | Obrigatória. Veja abaixo como gerar |
| `DJANGO_DEBUG` | `1` no desenvolvimento, `0` em produção |
| `DJANGO_ALLOWED_HOSTS` | Domínios separados por vírgula. Obrigatória quando `DJANGO_DEBUG=0` |
| `BREVO_API_KEY` | Obrigatória. Chave da API transacional do Brevo |
| `EMAIL_REMETENTE` | Remetente das mensagens, no formato `Nome <endereco@dominio>` |

Para gerar a chave secreta:

```
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

A aplicação não sobe sem `DJANGO_SECRET_KEY` e `BREVO_API_KEY`. A falha aparece como `ImproperlyConfigured` já no `manage.py check`, com a instrução do que preencher.

## Email

O envio acontece apenas pela API do Brevo, em `configuracao/email.py`. Cada mensagem vira um `POST` para `https://api.brevo.com/v3/smtp/email`, com a chave no cabeçalho `api-key` e o destinatário definido no momento do envio, sem lista de contatos.

Escrito como backend de email do Django, o que mantém as views usando `send_mail` normalmente. A mensagem de recuperação de senha tem versão em texto e versão em HTML, e a segunda é a que vai no `htmlContent`.

Dois pontos costumam derrubar o envio na primeira tentativa.

Se a conta tiver restrição por IP ativa, o Brevo responde 401 até que o endereço de onde parte a requisição seja autorizado em https://app.brevo.com/security/authorised_ips. Vale para a máquina de desenvolvimento e para o Render, e o endereço IPv6 precisa ser autorizado junto com o IPv4, porque a saída pode usar qualquer um dos dois.

O endereço em `EMAIL_REMETENTE` precisa estar verificado na conta. Quando não está, a API responde sucesso e descarta a mensagem depois, na fila de envio. Nada aparece no log do servidor nesse caso, e o motivo só é visível no log de eventos da conta, em Transactional, Logs, ou pelo endpoint `GET /v3/smtp/statistics/events`.

Quando o envio falha, o Django registra o erro no log e ainda assim mostra a tela de confirmação ao usuário, para não revelar quais emails têm cadastro. Ao testar recuperação de senha, acompanhe o terminal do servidor.

## Organização

```
autenticacao/    usuário, formulários, views e rotas de acesso
catalogo/        variáveis, domínios de valores e operadores de comparação
estudos/         estudos, critérios e seletor de variáveis
configuracao/    settings, urls do projeto e backend de email
templates/       layouts e telas de cada app
static/css/      folha de estilo sobre o Bootstrap
static/js/       seletor de variáveis e campos do formulário de critério
```

O modelo de usuário é próprio, com email como identificador e nome completo obrigatório. O cadastro é aberto a quem tem email `@alunos.umc.br` e a pessoa escolhe o próprio perfil no formulário. O administrador pode corrigir o perfil de qualquer conta pelo admin.

Cada conta tem um perfil, pesquisador ou profissional, e ele decide o que a pessoa alcança. O profissional chega ao registro de dados e à relação de pendências. O pesquisador chega aos estudos e aos critérios de cada um. Quem não tem o perfil recebe 403, mesmo digitando a URL direto, porque a verificação está no decorador `exige_perfil`, em `autenticacao/permissoes.py`, aplicado na view.

Entre pesquisadores, cada um enxerga apenas os próprios estudos. O estudo de outra pessoa responde 404, para não confirmar que ele existe.

## Testes

pytest, com os testes em arquivos `teste_*.py`.

```
.venv\Scripts\python.exe -m pytest
```

Os testes atuais, todos em `estudos/teste_seletor_variavel.py`, cobrem a navegação e a busca no seletor de variáveis, a gravação de critérios de data em cada precisão (incluindo a recusa de data que não existe no calendário) e a negativa de acesso ao seletor, tanto para o profissional quanto para o pesquisador que não é dono do estudo. Cadastro, login e as demais telas de estudo ainda estão sem testes.
