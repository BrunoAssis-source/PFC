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

Faltam o cadastro de voluntários, os valores coletados e a verificação de elegibilidade. Por isso as telas do profissional, registro de dados e pendências, existem ainda sem conteúdo.

O app `auditoria` registra login com sucesso e com falha, logout, criação de conta, redefinição de senha, negação de acesso por perfil insuficiente e leitura ou edição de estudo. Cada registro grava usuário, ação, IP e data. A tela fica em `/auditoria/`, aberta a quem tem `is_staff`, do jeito que o Django admin já reconhece como administrador, sem depender do perfil de pesquisador ou profissional. Pelo admin do Django o mesmo registro aparece sem opção de editar nem excluir.

Ainda faltam três pontos de auditoria: troca de senha por quem já está logado (hoje só existe o fluxo de redefinição por email), edição de critério (a tela atual só cria e remove, não edita) e acesso a variável marcada como sensível (o campo `sensivel` existe no catálogo, mas nenhuma tela ainda lê ou restringe por ele). Cada um entra na auditoria quando a funcionalidade correspondente existir.

Política de privacidade e termos de uso são páginas próprias, abertas sem login, e o cadastro exige a leitura dos dois antes de criar conta. A política já descreve o que está implementado (dado de conta) e o que está previsto para quando o cadastro de participante existir (CPF cifrado, pseudonimização por HMAC-SHA256, prazo de retenção ligado ao estudo ativo), deixando explícito o que é real e o que é desenho futuro.

## Stack

Django 5.2 no padrão MVT, PostgreSQL, Bootstrap 5 e pytest. Aplicação monolítica, sem API própria, porque o único cliente é o navegador.

O envio de email usa a API transacional do Brevo, com requisição HTTP direta em um backend de email do Django.

Em produção: Render para a aplicação e Neon para o banco.

## Como executar

Requer Python 3.14 e Docker, usado apenas para o banco. O Django roda na máquina local.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copie o `.env.example` para `.env` e preencha as variáveis descritas abaixo, inclusive `DB_PASSWORD`. Depois:

```
docker compose up -d
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver
```

O `docker compose up -d` sobe o PostgreSQL 16 com um volume nomeado, então os dados sobrevivem a `docker compose down`. O `migrate` já carrega o catálogo de variáveis e ativa as extensões `unaccent` e `pg_trgm`, usadas na busca de critérios. Se a porta 5432 já estiver ocupada por outro PostgreSQL na máquina, troque `DB_PORT` no `.env` (por exemplo para 5433) antes de subir o container.

O `createsuperuser` pede email antes do nome, porque o email é o campo de identificação do usuário no lugar do nome de acesso padrão do Django.

A aplicação responde em http://127.0.0.1:8000. A raiz é a tela de login, e o admin do Django fica em `/admin/`. Política de privacidade (`/politica-de-privacidade/`) e termos de uso (`/termos-de-uso/`) abrem sem login.

## Variáveis de ambiente

Ficam no arquivo `.env`, na raiz, que não é versionado. O `settings.py` lê esse arquivo na subida; variável já definida no ambiente tem precedência sobre o que estiver escrito nele.

| Variável | Uso |
|---|---|
| `DJANGO_SECRET_KEY` | Obrigatória. Veja abaixo como gerar |
| `DJANGO_DEBUG` | `1` no desenvolvimento, `0` em produção |
| `DJANGO_ALLOWED_HOSTS` | Domínios separados por vírgula. Obrigatória quando `DJANGO_DEBUG=0` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexão com o PostgreSQL. O `docker-compose.yml` cria o banco com os mesmos valores |
| `BREVO_API_KEY` | Chave da API transacional do Brevo. Obrigatória apenas quando `DJANGO_DEBUG=0` |
| `EMAIL_REMETENTE` | Remetente das mensagens, no formato `Nome <endereco@dominio>` |

Para gerar a chave secreta:

```
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

A aplicação não sobe sem `DJANGO_SECRET_KEY`. A falha aparece como `ImproperlyConfigured` já no `manage.py check`, com a instrução do que preencher. `BREVO_API_KEY` só é exigida com `DJANGO_DEBUG=0`; no desenvolvimento, deixá-la vazia manda o email para o terminal.

## Email

Em produção o envio acontece apenas pela API do Brevo, em `configuracao/email.py`. No desenvolvimento sem `BREVO_API_KEY` o Django usa o backend de console e escreve a mensagem inteira no terminal, o que basta para conferir o link de recuperação de senha. Cada mensagem vira um `POST` para `https://api.brevo.com/v3/smtp/email`, com a chave no cabeçalho `api-key` e o destinatário definido no momento do envio, sem lista de contatos.

Escrito como backend de email do Django, o que mantém as views usando `send_mail` normalmente. A mensagem de recuperação de senha tem versão em texto e versão em HTML, e a segunda é a que vai no `htmlContent`.

Dois pontos costumam derrubar o envio na primeira tentativa.

Se a conta tiver restrição por IP ativa, o Brevo responde 401 até que o endereço de onde parte a requisição seja autorizado em https://app.brevo.com/security/authorised_ips. Vale para a máquina de desenvolvimento e para o Render, e o endereço IPv6 precisa ser autorizado junto com o IPv4, porque a saída pode usar qualquer um dos dois.

O endereço em `EMAIL_REMETENTE` precisa estar verificado na conta. Quando não está, a API responde sucesso e descarta a mensagem depois, na fila de envio. Nada aparece no log do servidor nesse caso, e o motivo só é visível no log de eventos da conta, em Transactional, Logs, ou pelo endpoint `GET /v3/smtp/statistics/events`.

Quando o envio falha, o Django registra o erro no log e ainda assim mostra a tela de confirmação ao usuário, para não revelar quais emails têm cadastro. Ao testar recuperação de senha, acompanhe o terminal do servidor.

## Organização

```
autenticacao/    usuário, formulários, views e rotas de acesso
auditoria/       registro de eventos de acesso e de uso
catalogo/        variáveis, domínios de valores e operadores de comparação
estudos/         estudos, critérios e seletor de variáveis
configuracao/    settings, urls do projeto e backend de email
templates/       layouts e telas de cada app
static/css/      folha de estilo sobre o Bootstrap
static/js/       seletor de variáveis e campos do formulário de critério
```

O modelo de usuário é próprio, com email como identificador e nome completo obrigatório. O cadastro é aberto a quem tem email `@alunos.umc.br` e a pessoa escolhe o próprio perfil no formulário. A conta feita pelo próprio visitante nasce inativa e só passa a valer quando ele confirma o email, pelo link ou pelo código de 8 caracteres que a mensagem traz. O código vale 30 minutos e o link 3 dias. Cada envio gera os dois de novo e cancela os anteriores. A tabela `ConfirmacaoEmail` guarda só o hash de cada um, com o horário do envio e as contagens do limitador: 60 segundos entre pedidos, no máximo 5 envios por hora e 5 tentativas erradas por código, depois das quais é preciso pedir outro. O Brevo reescreve os links do email para medir cliques e não há opção por mensagem para desligar isso, por isso o código existe como segundo caminho. Quem tenta entrar antes de confirmar recebe o aviso e pode pedir o envio de novo na tela de login. Contas criadas pelo administrador ficam ativas na hora. O administrador pode corrigir o perfil de qualquer conta pelo admin ou pela tela de usuários.

Cada conta tem um perfil, pesquisador ou profissional, e ele decide o que a pessoa alcança. O profissional chega ao registro de dados e à relação de pendências. O pesquisador chega aos estudos e aos critérios de cada um. Quem não tem o perfil recebe 403, mesmo digitando a URL direto, porque a verificação está no decorador `exige_perfil`, em `autenticacao/permissoes.py`, aplicado na view.

Entre pesquisadores, cada um enxerga apenas os próprios estudos. O estudo de outra pessoa responde 404, para não confirmar que ele existe.

## Testes

pytest, com os testes em arquivos `teste_*.py`.

```
.venv\Scripts\python.exe -m pytest
```

Os testes rodam no PostgreSQL do container, que precisa estar no ar. O pytest cria e descarta um banco de teste à parte, sem tocar nos dados de desenvolvimento.

Os testes atuais, todos em `estudos/teste_seletor_variavel.py`, cobrem a navegação e a busca no seletor de variáveis, a gravação de critérios de data em cada precisão (incluindo a recusa de data que não existe no calendário) e a negativa de acesso ao seletor, tanto para o profissional quanto para o pesquisador que não é dono do estudo. Cadastro, login e as demais telas de estudo ainda estão sem testes.
