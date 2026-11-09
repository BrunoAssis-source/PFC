# UniData

Sistema web para orientar a coleta de dados de voluntários de pesquisa a partir dos critérios de elegibilidade definidos por cada estudo.

O pesquisador cadastra um estudo, as variáveis que ele exige e seus critérios. O profissional registra os dados de cada voluntário e o sistema verifica a compatibilidade durante o preenchimento, interrompendo quando um critério deixa de ser atendido. Os dados já registrados ficam disponíveis para outros estudos enquanto houver pesquisa ativa vinculada ao voluntário.

A classificação produzida pelo sistema é sugestão. A decisão sobre quem entra em um estudo é do pesquisador e fica registrada.

Projeto Final de Curso do Bacharelado em Sistemas de Informação da Universidade de Mogi das Cruzes.

Autor: Bruno de Faria Assis.

## Estado atual

Estão implementados a autenticação com controle de acesso por perfil, o catálogo de variáveis e o cadastro de estudos e critérios.

A autenticação cobre o cadastro restrito ao domínio `@alunos.umc.br`, login, recuperação de senha por email e a separação entre pesquisador e profissional, com as rotas de cada um negando acesso a quem não tem o perfil.

O pesquisador cadastra e edita estudos, cada um com situação de rascunho, ativo ou encerrado. Os critérios de elegibilidade ficam numa tela só, com três colunas: o catálogo de variáveis à esquerda, a condição do critério ao centro e a lista do estudo à direita. O catálogo aparece em árvore (domínio, grupo, variável) ou, com a busca preenchida, como lista de resultados. A busca aceita sinônimos ("grau de instrução" acha Escolaridade), ignora acento e caixa e tolera erro de digitação, tudo no PostgreSQL, com as extensões `unaccent` e `pg_trgm`. Se nada é encontrado, o pesquisador pode propor uma variável nova, que entra no catálogo e fica disponível para qualquer estudo.

Cada critério é de inclusão ou de exclusão, e a condição muda conforme o tipo da variável:

| Tipo | Como o pesquisador define a condição |
|---|---|
| Numérica | entre (dois valores), pelo menos, no máximo ou exatamente, com a unidade ao lado |
| Categórica nominal | caixas de seleção com as opções cadastradas, com botões para marcar todas e limpar |
| Categórica ordinal | a partir de, até ou exatamente, mais a escolha de um nível da lista ordenada |
| Booleana | sim ou não |

Uma caixa "Como vai ficar" mostra a frase do critério enquanto ele é montado, por exemplo "Incluir participantes com idade entre 18 e 65 anos." O botão de adicionar só habilita quando a condição está completa, e o aviso diz o que falta. A frase e a validação vêm do servidor, do mesmo formulário que grava o critério, para existirem num lugar só. À direita, o resumo reúne tudo em texto corrido. A idade é uma variável só, em anos. Data de nascimento e faixa etária ficam fora da tela, e o pesquisador nunca informa datas.

Município de residência é escolhido em cascata: primeiro o estado, depois os municípios dele, com filtro pelo nome. A seleção atravessa estados, então um mesmo critério pode juntar cidades de lugares diferentes. A lista é a oficial do IBGE (27 estados e 5.571 municípios, consultada em novembro de 2026) e está em `catalogo/dados/`, carregada por migration como dado fixo do sistema. Em funcionamento a aplicação não consulta nenhuma API externa, e para atualizar a lista basta gerar os dois arquivos de novo a partir da API de localidades do IBGE e criar uma migration.

Cada regra da lista à direita tem Editar e Remover. Editar abre o critério na coluna do meio com os valores atuais, e a variável fica fixa: para usar outra, remove-se o critério e adiciona-se um novo. Tudo o mais pode mudar, como incluir ou excluir, a condição e os valores. Remover pede confirmação na própria linha, com "Sim, remover" e "Não", e o Esc desiste.

A tela recusa o critério que não restringe ninguém. Numa lista de opções, marcar todas dá o aviso "Esse critério inclui todos os participantes" (ou "exclui", quando a regra é de exclusão). Numa escala de níveis, vale o mesmo para "a partir do nível mais baixo" e "até o nível mais alto". Também é recusado o critério idêntico a outro do mesmo estudo, com a mesma variável, regra, condição e valores. Os dois avisos aparecem na prévia, que desabilita o botão, e o servidor repete a checagem.

Algumas variáveis sim ou não têm texto próprio para cada resposta, para a frase sair natural. Pessoa com deficiência produz "com deficiência" e "sem deficiência", em vez de "pessoa com deficiência: sim". A prévia vai por POST, com o formulário inteiro no corpo, porque uma lista grande de municípios não cabe no endereço da requisição.

O mesmo critério pode se repetir no estudo, por exemplo idade mínima na inclusão e idade máxima na exclusão. Variável de texto livre não serve de critério.

O profissional identifica o voluntário em `/voluntarios/`, pelo CPF e só por ele, sem nome nem contato. O sistema valida os dígitos, calcula o código HMAC-SHA256 e procura por esse código. Se o voluntário existe, a tela abre o cadastro dele. Se não existe, oferece cadastrar. O CPF é gravado cifrado (Fernet) ao lado do código, que tem restrição de unicidade no banco, então o mesmo CPF não gera dois voluntários nem quando dois profissionais cadastram ao mesmo tempo. Na tela o CPF aparece mascarado (`***.982.247-**`) e só os 11 dígitos digitados na busca passam pelo servidor.

O voluntário é vinculado a um estudo ativo com o aceite do TCLE. O profissional marca que conferiu o documento físico assinado, e o sistema grava a versão do termo, a data e quem registrou. Sem a marcação não há participação, e o mesmo voluntário não entra duas vezes no mesmo estudo. Qualquer profissional pode vincular voluntário a qualquer estudo ativo.

A auditoria registra busca, cadastro, tentativa de cadastro repetido, leitura da ficha e vínculo com TCLE. O objeto do registro leva só os oito primeiros caracteres do código, nunca o CPF.

Na ficha do voluntário, o botão Coletar dados abre a coleta da participação, uma variável por tela. As variáveis perguntadas são as dos critérios do estudo, com as não sensíveis primeiro e as sensíveis por último, para quem seria eliminado nunca responder uma pergunta sensível. Variável derivada não é perguntada. Idade, faixa etária e renda per capita saem das origens (data de nascimento, renda familiar e pessoas no domicílio) a cada consulta, então a idade acompanha o calendário e nada disso fica gravado.

Cada resposta é gravada e conferida na mesma transação. A conferência é feita no banco, pela view `voluntarios_avaliacao_criterio`, que compara o valor com os critérios do estudo nos 15 operadores. Inclusão exige atender e exclusão exige não atender. Se algum critério reprova, a gravação é desfeita, de modo que a resposta que eliminou nunca fica no banco, e as respostas anteriores, que passaram, ficam. A participação passa a `eliminada` e guarda o critério reprovado. Quando todas as variáveis são respondidas e nenhuma reprova, a participação passa a `concluida`.

O profissional não vê o resultado da verificação. A tela de eliminação diz apenas "Coleta encerrada: este voluntário não é compatível com o estudo.", igual para qualquer critério e para variável comum ou sensível, e a ficha mostra a participação como encerrada. Os testes comparam o conteúdo da tela, o redirecionamento e o número de consultas entre os casos. O critério que eliminou aparece só para o pesquisador, na tela do estudo, junto do código curto do voluntário.

Os valores coletados ficam em linhas (voluntário, variável, valor, fonte, data), ligados ao voluntário só pelo código HMAC. Valor novo da mesma variável é linha nova, e a verificação usa a mais recente.

Variável marcada como sensível (identidade de gênero, orientação sexual, pessoa com deficiência e raça ou cor) vai para a tabela `ValorSensivel`, com a mesma estrutura e sem cifra de coluna. A decisão tem quatro razões. O domínio de cada variável é uma lista fechada, então cifrar o valor esconderia pouco. A verificação e o reaproveitamento entre estudos comparam valores no banco, o que a cifra impediria. A tabela separada isola esses dados do restante. E o acesso é auditado, com o banco cifrado em repouso pelo provedor. A auditoria registra cada resposta a variável sensível, com o código da variável e o código curto do voluntário, nunca o valor.

Faltam a classificação em elegível, pendente ou inelegível nos estudos que reaproveitam dados e a tela de pendências.

O app `auditoria` registra login com sucesso e com falha, logout, criação de conta, redefinição de senha, negação de acesso por perfil insuficiente e leitura ou edição de estudo, e também adição, edição e remoção de critério. Cada registro grava usuário, ação, IP e data. A tela fica em `/auditoria/`, aberta a quem tem `is_staff`, do jeito que o Django admin já reconhece como administrador, sem depender do perfil de pesquisador ou profissional. Pelo admin do Django o mesmo registro aparece sem opção de editar nem excluir. O texto do objeto não tem limite de tamanho, porque na edição de critério o registro guarda a frase antes e depois, e uma lista de municípios passa de 150 caracteres. Se a edição não muda a frase, nada é registrado.

A leitura de valor sensível por outra tela, como a do pesquisador, ainda não existe. Quando existir, deve entrar na auditoria como a gravação já entra.

### Trabalho futuro na coleta

- Retomada de participação interrompida. A situação `interrompida` existe, mas nenhuma tela a aplica. Hoje a coleta em andamento continua de onde parou ao ser aberta de novo, sem um passo explícito de interromper.
- Fluxo de fonte confirmada. A fonte é gravada em cada resposta, mas nada ainda distingue fonte confirmada de informada pelo voluntário. O estado pendente dos estudos auxiliares depende disso.
- Variáveis exigidas além dos critérios. O estudo só pergunta as variáveis que aparecem em critérios.
- Seleção de município. A lista tem 5.571 opções em uma caixa de seleção única, sem a cascata por estado que a tela de critérios tem.

### Trabalho futuro na identificação de voluntários

- Revogação do TCLE. A situação `revogada` existe na participação, mas nenhuma tela a aplica. Falta decidir o que acontece com os dados já coletados.
- Designação de profissional por estudo. Hoje qualquer profissional vincula voluntário a qualquer estudo ativo.
- Texto do TCLE no sistema. A versão é uma constante em `voluntarios/models.py`, e o termo em si fica no documento físico do comitê de ética.
- Rotação das chaves. Trocar `CHAVE_HMAC` ou `CHAVE_CIFRA` exige recalcular os registros existentes, e não há comando para isso.

### Trabalho futuro nos critérios

Ficaram de fora, por decisão de escopo, estes itens.

- Aviso de contradição entre critérios. Hoje o sistema só recusa o critério duplicado. Condições que se anulam passam sem aviso, como incluir idade de pelo menos 30 anos e incluir idade de no máximo 20, ou incluir e excluir a mesma condição. O aviso deve apontar o par em conflito e valer na prévia e no servidor, como as outras checagens.
- Regras por situação do estudo. Hoje é possível adicionar, editar e remover critério em estudo de qualquer situação. A proposta é deixar rascunho livre, pedir confirmação com aviso em estudo ativo e tornar o estudo encerrado somente leitura, inclusive para adicionar.
- Motivo da alteração. Em estudo ativo, pedir ao pesquisador a razão da mudança e gravá-la no registro de auditoria.
- Travamento por triagem iniciada. Quando existir verificação de elegibilidade, o critério de um estudo com triagem não deve mudar. Alterar passaria a exigir uma nova versão do estudo. Hoje não há dado de triagem para detectar isso.
- Histórico e desfazer. A remoção apaga o critério de verdade, e só o registro de auditoria guarda a frase. Manter os critérios removidos ou alterados como versões permitiria consultar o estudo como ele estava em uma data e desfazer uma remoção.

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
| `CHAVE_HMAC`, `CHAVE_CIFRA` | Obrigatórias. Veja abaixo como gerar |
| `BREVO_API_KEY` | Chave da API transacional do Brevo. Obrigatória apenas quando `DJANGO_DEBUG=0` |
| `EMAIL_REMETENTE` | Remetente das mensagens, no formato `Nome <endereco@dominio>` |

Para gerar a chave secreta:

```
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

As duas chaves do CPF são independentes. `CHAVE_HMAC` gera o código de busca e `CHAVE_CIFRA` cifra o CPF. Gere cada uma uma vez, só no ambiente em que vai usar:

```
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

O primeiro comando serve para `CHAVE_HMAC` e o segundo para `CHAVE_CIFRA`. Guarde as duas fora do repositório, num gerenciador de senhas. Perder a `CHAVE_CIFRA` torna os CPFs cifrados irrecuperáveis, e trocar a `CHAVE_HMAC` faz a busca deixar de achar os voluntários já cadastrados. Cada ambiente tem as suas, então um banco não abre com a chave de outro.

A aplicação não sobe sem `DJANGO_SECRET_KEY`, `CHAVE_HMAC` e `CHAVE_CIFRA`. A falha aparece como `ImproperlyConfigured` já no `manage.py check`, com a instrução do que preencher. `BREVO_API_KEY` só é exigida com `DJANGO_DEBUG=0`; no desenvolvimento, deixá-la vazia manda o email para o terminal.

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
estudos/         estudos e a tela de critérios de elegibilidade
configuracao/    settings, urls do projeto e backend de email
templates/       layouts e telas de cada app
static/css/      folha de estilo sobre o Bootstrap
static/js/       interação da tela de critérios
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

Os testes cobrem a busca do catálogo (sinônimo, acento, erro de digitação, variáveis que ficam fora), a frase de cada tipo de critério e do resumo do estudo, a validação de critério incompleto e a tela de critérios de ponta a ponta: configuração, prévia, adicionar e remover. O controle de acesso tem testes próprios, que confirmam o 403 para o profissional, o 404 para o estudo de outra pesquisadora e o redirecionamento do visitante, em todas as rotas da tela.

Também há testes para editar critério (tela preenchida por tipo, gravação, validação e acesso), para a confirmação de remoção e para o log das três ações. A simulação do navegador usada para conferir o script da tela não está automatizada.

Ainda sem testes: cadastro, login, confirmação de email, gestão de usuários e as telas de lista e edição de estudo. A avaliação de um participante contra os critérios depende do cadastro de voluntários, que não existe.
