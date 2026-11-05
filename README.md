# Pão de Cada Dia

Vitrine gratuita de compra e venda entre estudantes do Campus Paraíso (UFLA/ICTIN, MG).
Quem visita encontra a oferta e chama o vendedor no WhatsApp, sem cadastro. Quem vende
mantém os anúncios com um clique. A administração aprova o primeiro anúncio de cada
vendedor e trata denúncias.

Stack: Python 3.14, Django 5.2 LTS, PostgreSQL 17, templates renderizados no servidor,
whitenoise e gunicorn. Detalhes em `docs/produto/planos/vitrine-mvp.md`.

## Rodar localmente

Pré-requisito: Docker com Compose v2 ou mais novo.

```sh
docker compose up
```

Abra http://localhost:8000. Na primeira vez a imagem é construída, o banco é criado,
as migrações rodam e os dados de exemplo (marcados "(exemplo)") são carregados. O
código fica montado no container: editar um arquivo recarrega o servidor.

- Não precisa de `.env` para desenvolver. Para mudar algo, copie `cp .env.example .env`
  e preencha só o que quiser; variável em branco usa o padrão.
- Porta 8000 ocupada? `WEB_PORT=8080 docker compose up`. A porta é publicada só em
  `127.0.0.1`: outras máquinas da rede não acessam o app.
- Para tirar os dados de exemplo de um banco que já os tem:
  `docker compose run --rm web python manage.py load_demo --remove`. Depois, suba com
  `DEMO_DATA=false docker compose up` (ou ponha `DEMO_DATA=false` no `.env`): com o padrão
  `DEMO_DATA=true`, o `docker/start-dev.sh` carrega tudo de novo no próximo `up`. Com
  `DEMO_DATA=false` eles também deixam de aparecer na vitrine, mesmo sem o `--remove`.
- Guia de estilos (só com `DEBUG=true`): http://localhost:8000/_estilos/

### Criar o administrador

Não existe login padrão. Com o app no ar, em outro terminal:

```sh
docker compose exec web python manage.py createsuperuser
```

Informe e-mail e senha. Depois entre em http://localhost:8000/entrar/ e acesse
http://localhost:8000/admin/ (área de administração própria do site; o Django admin
não é instalado). Para trocar a senha de alguém: `docker compose exec web python
manage.py changepassword <email>`.

### Testes e verificação

```sh
docker compose run --rm web scripts/verify.sh      # ruff, checks, migrações, check --deploy, pytest
docker compose run --rm web pytest                 # só a suíte
docker compose run --rm web pytest apps/core/tests/test_ratelimit.py -q   # um arquivo
```

Fora do Docker (usa SQLite):

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest
```

Os testes não usam serviço externo: fotos ficam em memória, e-mail em memória e o
relógio é controlado com `time-machine`.

### Comandos úteis

```sh
docker compose exec web python manage.py makemigrations   # nova migração (arquivo fica com o seu usuário)
docker compose logs -f web
docker compose down          # para tudo (os dados ficam nos volumes)
docker compose down -v       # para e APAGA banco e fotos locais
```

## Publicar

A mesma imagem (`Dockerfile`) serve para produção: ela roda `migrate`, apaga dados
vencidos (`cleanup_data`, abaixo) e sobe o gunicorn (`docker/start.sh`). Na imagem, o
código pertence ao root; o app roda como o usuário `app` e só escreve nos estáticos e
na pasta de fotos. Em todas as opções:

1. Gere uma `SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`.
2. Defina `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` com o seu domínio.
3. Com HTTPS terminado por proxy (todas as opções abaixo), use
   `SECURE_PROXY_SSL_HEADER=true` e `TRUSTED_PROXY_HOPS=1`. Depois de confirmar que o
   HTTPS funciona, ligue `SECURE_HSTS_SECONDS=31536000`.
4. As fotos precisam de armazenamento persistente: volume (padrão,
   `STORAGE_BACKEND=local`) ou bucket S3 (`STORAGE_BACKEND=s3`; AWS, Cloudflare R2,
   Tigris ou Backblaze B2). Em PaaS sem volume, os arquivos somem a cada deploy. Em
   plataforma sem disco persistente, como a Vercel, o bucket (R2) é obrigatório.
5. Crie o administrador com `python manage.py createsuperuser` no ambiente publicado.
6. Preencha `PRIVACY_CONTROLLER_NAME` (quem responde pelos dados) e
   `PRIVACY_CONTACT_EMAIL` (contato para pedidos sobre dados pessoais; também aparece
   em "Entrar", "Recuperar senha" desligada e no aviso de cadastros esgotados). Vazias,
   a página `/privacidade/` mostra "Responsável: a definir", as outras telas dizem que
   ainda não há contato e `check --deploy` avisa.
7. Recuperação de senha: só funciona com um provedor de e-mail.
   - Sem SMTP (padrão, `EMAIL_BACKEND` de console) e com `DEBUG=false`, ela fica
     **desligada**: o link "Esqueceu a senha?" some e a página pede para falar com a
     administração, que troca a senha com
     `python manage.py changepassword <email>`. Isso evita que o link com o token
     vá parar no log.
   - Antes de trocar a senha a pedido de alguém, confira a identidade: só atenda
     pedido que chegue do próprio e-mail da conta e envie a senha nova só para esse
     e-mail. Sem isso, qualquer pessoa que se passe pelo vendedor toma a conta.
   - Para ligar, use `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` e
     preencha `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
     `EMAIL_USE_TLS` e `DEFAULT_FROM_EMAIL` com os dados do provedor.
8. Cadastro: no máximo `SIGNUPS_PER_DAY` contas novas por dia no site inteiro
   (padrão 50; `0` fecha o cadastro).

Todas as variáveis estão explicadas em `.env.example`. O log do gunicorn não registra
IP nem query string, e o caminho `/senha/redefinir/...` sai mascarado
(`/senha/redefinir/***`) nos logs do gunicorn e do Django.

### Limpeza de dados vencidos

`python manage.py cleanup_data` apaga sessões vencidas, contadores do limite de
tentativas vencidos, buscas sem resultado com mais de 90 dias e o texto das
denúncias tratadas há mais de 180 dias (prazos em `apps/core/retention.py`, os mesmos
da página de privacidade). Ele roda a cada subida do app, mas isso não basta: o container
pode passar meses sem reiniciar e a página de privacidade promete esses prazos. Por isso,
o cron é necessário em produção para cumprir os prazos. Rode de hora em hora: sem
movimento no site, só o cron apaga os contadores do limite de tentativas. Os que têm
código de IP, e-mail ou conta vencem com 23 h, para que, com uma rodada por hora,
nenhum passe das 24 h prometidas; com o cron diário um contador poderia durar quase
48 h. O contador do teto de cadastros do dia não tem dado pessoal e fica até o dia
virar. Na VPS:

```sh
# crontab -e  (de hora em hora, no minuto 7)
7 * * * * cd /caminho/do/projeto && docker compose -f compose.yaml -f compose.prod.yaml exec -T web python manage.py cleanup_data
```

No Fly.io e no Railway, o agendador da plataforma é igualmente necessário, de hora em hora e com o
mesmo comando (`python manage.py cleanup_data`).

Na Vercel não há shell nem crontab: a limpeza roda pela rota `/_tarefas/limpeza/`, que
exige `CRON_SECRET`. O `vercel.json` a agenda 1 vez por dia (o limite do plano Hobby) e
o GitHub Actions (`.github/workflows/limpeza.yml`) a chama de 30 em 30 minutos. Detalhes em
"Vercel", abaixo. Sem `CRON_SECRET` a rota responde 404, então nas outras opções ela
fica desligada.

### Opção recomendada: VPS pequena com Docker e Caddy

1. Instale Docker e Caddy na VPS, aponte o DNS do domínio para ela e clone o projeto.
2. Crie o `.env` a partir do `.env.example` com, no mínimo: `SECRET_KEY`,
   `ALLOWED_HOSTS=seu.dominio`, `CSRF_TRUSTED_ORIGINS=https://seu.dominio`,
   `POSTGRES_PASSWORD` (longa e aleatória), `SECURE_PROXY_SSL_HEADER=true`,
   `TRUSTED_PROXY_HOPS=1`, `PRIVACY_CONTROLLER_NAME` e `PRIVACY_CONTACT_EMAIL`.
3. Suba:
   ```sh
   docker compose -f compose.yaml -f compose.prod.yaml up -d --build
   docker compose -f compose.yaml -f compose.prod.yaml exec web python manage.py createsuperuser
   ```
   O app escuta só em `127.0.0.1:8000`; banco e fotos ficam nos volumes `pgdata` e `media`.
4. `/etc/caddy/Caddyfile` (o Caddy obtém o certificado HTTPS sozinho):
   ```
   seu.dominio {
       request_body {
           max_size 20MB
       }
       reverse_proxy 127.0.0.1:8000
   }
   ```
   `sudo systemctl reload caddy`. O limite de 20 MB cobre 3 fotos de 5 MB e o formulário.
5. Atualizar: `git pull && docker compose -f compose.yaml -f compose.prod.yaml up -d --build`.
6. Backup do banco:
   `docker compose exec db pg_dump -U paodecadadia paodecadadia > backup.sql`
   (e copie o volume `media`, se usar fotos locais).

### Fly.io

1. `fly launch --no-deploy` (usa o `Dockerfile`; porta interna 8000).
2. Banco: `fly postgres create` e `fly postgres attach`, ou um Postgres gerenciado.
   O app lê `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` e
   `POSTGRES_PASSWORD` (não lê `DATABASE_URL`): defina-as com `fly secrets set`.
3. Fotos: `fly volumes create media --size 1` e, no `fly.toml`,
   `[mounts] source="media" destination="/data/media"`; ou um bucket Tigris
   (`fly storage create`) com `STORAGE_BACKEND=s3` e `AWS_S3_ENDPOINT_URL=https://fly.storage.tigris.dev`.
4. `fly secrets set SECRET_KEY=... ALLOWED_HOSTS=<app>.fly.dev CSRF_TRUSTED_ORIGINS=https://<app>.fly.dev SECURE_PROXY_SSL_HEADER=true TRUSTED_PROXY_HOPS=1 FORWARDED_ALLOW_IPS=*`
5. Health check: `GET /healthz` (responde 200 com o banco no ar).
6. `fly deploy` e depois `fly ssh console -C "python manage.py createsuperuser"`.

### Railway

1. Novo projeto a partir do repositório (o Railway detecta o `Dockerfile`).
2. Adicione o plugin PostgreSQL e, no serviço web, defina `POSTGRES_HOST=${{Postgres.PGHOST}}`,
   `POSTGRES_PORT=${{Postgres.PGPORT}}`, `POSTGRES_DB=${{Postgres.PGDATABASE}}`,
   `POSTGRES_USER=${{Postgres.PGUSER}}`, `POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}`.
3. Fotos: adicione um volume montado em `/data/media` ou use S3.
4. Variáveis: `SECRET_KEY`, `ALLOWED_HOSTS=<app>.up.railway.app`,
   `CSRF_TRUSTED_ORIGINS=https://<app>.up.railway.app`, `SECURE_PROXY_SSL_HEADER=true`,
   `TRUSTED_PROXY_HOPS=1`, `FORWARDED_ALLOW_IPS=*`. O Railway define `PORT`.
5. Health check path: `/healthz`. Admin: `railway run python manage.py createsuperuser`
   (ou pelo shell do serviço).

### Vercel

Na Vercel o app vira uma função Python (sem Docker, sem gunicorn, sem disco que dure).
O plano técnico completo está em `docs/produto/planos/publicar-vercel.md` e as decisões
do dono em `docs/produto/decisoes.md` ("Publicação na Vercel").

**Plano Hobby (gratuito), com risco aceito.** Os termos da Vercel restringem o Hobby a
uso pessoal não comercial e citam "advertising the sale of a product or service". O
dono aceitou o risco: a Vercel pode suspender o projeto, e a saída é passar para o Pro
ou para uma das opções com Docker acima. O Hobby também limita o cron a 1 vez por dia,
por isso a limpeza tem duas partes:

- o `vercel.json` chama `/_tarefas/limpeza/` 1 vez por dia (`7 6 * * *`, em UTC; no Hobby
  a Vercel pode disparar em qualquer minuto dessa hora);
- o GitHub Actions (`.github/workflows/limpeza.yml`) chama a mesma rota de 30 em 30 minutos,
  para cumprir as 24 h prometidas na página de privacidade. O GitHub pode atrasar ou
  descartar execuções agendadas quando está sobrecarregado, por isso o intervalo tem folga
  de uma rodada.

Se o GitHub Actions parar, só o cron diário da Vercel apaga os contadores. O pior caso é
de quase 2 dias: o contador vence com 23 h e espera até a próxima rodada diária, que no
Hobby pode cair em qualquer minuto da hora marcada (até 24 h 59 min depois da anterior).
Por isso a página de privacidade diz "em até 24 horas; se a limpeza automática falhar, em
até 2 dias" (`RATE_LIMIT_MAX_HOURS_IF_SCHEDULER_FAILS` em `apps/core/retention.py`).

**O que já está no repositório:**

- `pyproject.toml`: as dependências (cópia do `requirements.txt`; um teste impede que
  divirjam), Python 3.14, a entrada `config.wsgi:application` e o build
  `scripts/vercel_build.sh`.
- `scripts/vercel_build.sh`: só no build de produção, roda `migrate` pela conexão direta
  do Neon (`PGHOST_UNPOOLED`), não pelo pooler; depois, `check --deploy` no log. O
  `collectstatic` a Vercel roda sozinha e serve os estáticos pela CDN dela.
- `vercel.json`: região `gru1` (São Paulo), função com até 60 s, cron diário e
  `ignoreCommand`, que pula o build fora de produção. Assim nenhum preview usa o banco
  real (e nenhum preview é publicado). As migrações precisam continuar aditivas: o
  `migrate` roda com o código antigo ainda no ar, e o Instant Rollback não desfaz o esquema.
- `.vercelignore`: o `vercel deploy` pela CLI nunca envia `.env*` (só o `.env.example`).
- `/_tarefas/limpeza/`: roda o `cleanup_data` com o cabeçalho
  `Authorization: Bearer <CRON_SECRET>`; com outro valor, 401; sem `CRON_SECRET`, 404.

**Limites da Vercel que mudam o app:**

| Limite | Efeito | O que fazer |
|---|---|---|
| Corpo da requisição até 4,5 MB | Acima disso a Vercel responde com a página dela, e o formulário se perde | `MAX_UPLOAD_MB=1` (3 fotos × 1 MB + 1 MB = 4 MB) |
| Foto de celular tem mais de 1 MB | Seria recusada | O navegador reduz as fotos antes de enviar; sem JavaScript, cada foto pode ter até 1 MB |
| Sem disco persistente | Foto gravada no disco some | `STORAGE_BACKEND=s3` com Cloudflare R2 |
| Cron 1 vez por dia no Hobby | Os contadores passariam das 24 h | GitHub Actions de 30 em 30 minutos |
| Sem shell nem comando avulso | Não dá para rodar `createsuperuser` lá | Rodar da sua máquina com Docker (passo 8) |

**Banco: variáveis do Neon → variáveis do app.** O app não lê `DATABASE_URL`.

| O app lê | De onde vem na Vercel |
|---|---|
| `POSTGRES_HOST` | Injetada pelo Neon. Confira que é o host **com `-pooler`** |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Injetadas pelo Neon, com os mesmos nomes |
| `POSTGRES_DB` | **Manual**: o Neon injeta `POSTGRES_DATABASE`/`PGDATABASE` (ex.: `neondb`); copie o valor |
| `POSTGRES_PORT` | Padrão 5432; não precisa definir |
| `PGHOST_UNPOOLED` | Injetada pelo Neon; usada só pelo `scripts/vercel_build.sh` no `migrate` |
| `PGSSLMODE=require`, `PGCHANNELBINDING=require` | **Manuais**; o driver do PostgreSQL lê direto |
| `DB_DISABLE_SERVER_SIDE_CURSORS=true` | **Manual**; o pooler do Neon perde cursores entre transações |

**O que o dono faz nos painéis** (nada disso está criado):

1. Na Vercel, no plano Hobby, importe o repositório `Pedro-viniicius/projeto_hipocrita`
   (Git, branch `main`). O preset Django é detectado.
2. Marketplace → Neon → banco em **AWS São Paulo (`aws-sa-east-1`)**, ligado só ao
   ambiente Production. No SQL Editor do Neon, rode
   `ALTER DATABASE <nome> SET timezone TO 'UTC';` (o pooler perderia o ajuste de fuso
   feito por conexão).
3. Confira as variáveis que o Neon injetou e acrescente `POSTGRES_DB=<valor de PGDATABASE>`,
   `PGSSLMODE=require`, `PGCHANNELBINDING=require` e `DB_DISABLE_SERVER_SIDE_CURSORS=true`.
4. Cloudflare → R2: crie um bucket **privado** e um token de API "Object Read & Write"
   **restrito a esse bucket**. Na Vercel, no ambiente Production: `STORAGE_BACKEND=s3`,
   `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY` (estas duas como
   **Sensitive**), `AWS_S3_REGION_NAME=auto` e
   `AWS_S3_ENDPOINT_URL=https://<conta>.r2.cloudflarestorage.com`. As fotos saem por URLs
   assinadas e temporárias, como em qualquer S3.
5. Variáveis do app, no ambiente Production (marque as secretas como **Sensitive**):
   - `SECRET_KEY`: nova, gerada só para a Vercel (não reaproveite a de outro ambiente);
   - `ALLOWED_HOSTS=<projeto>.vercel.app` e `CSRF_TRUSTED_ORIGINS=https://<projeto>.vercel.app`
     (**nunca** `*.vercel.app`: qualquer pessoa cria um projeto nesse domínio). Com domínio
     próprio, acrescente-o às duas;
   - `SECURE_PROXY_SSL_HEADER=true`, `TRUSTED_PROXY_HOPS=1` (a Vercel troca o
     `X-Forwarded-For` pelo IP do visitante) e `MAX_UPLOAD_MB=1`;
   - `CRON_SECRET`: gere com `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
     e guarde o valor, porque a Vercel não o mostra de novo. O `check --deploy` avisa
     (`core.W002`) se ele tiver menos de 32 caracteres ou caractere fora de letras sem
     acento, números e `. _ ~ + / = -`;
   - `PRIVACY_CONTROLLER_NAME` e `PRIVACY_CONTACT_EMAIL`.

   **Não** defina `DEBUG` nem `DEMO_DATA`. Depois de confirmar o HTTPS, acrescente
   `SECURE_HSTS_SECONDS=31536000` e faça um novo deploy (a variável só vale a partir dele).
6. No GitHub, em Settings → Secrets and variables → Actions:
   - aba **Secrets**: `CRON_SECRET` com o mesmo valor da Vercel;
   - aba **Variables**: `SITE_URL=https://<projeto>.vercel.app` (com `https://`, sem barra
     no fim).
7. Faça push em `main`. No log do build, confira: "Python 3.14", dependências instaladas
   a partir do `pyproject.toml`, `migrate` rodou, `collectstatic` rodou e o `check --deploy`
   sem `core.W001` (responsável pelos dados) nem `core.W002` (formato do `CRON_SECRET`).
8. Administrador, sem shell na Vercel: na sua máquina, crie `.env.producao` (o
   `.gitignore` e o `.vercelignore` já o ignoram) com `POSTGRES_HOST=<host sem -pooler>`,
   `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PGSSLMODE=require`, `SECRET_KEY`
   (a mesma da Vercel) e `DEBUG=false`, e rode:
   ```sh
   docker build -t paodecadadia .
   docker run --rm -it --env-file .env.producao paodecadadia python manage.py createsuperuser
   ```
   Apague o `.env.producao` no fim. O mesmo vale para `changepassword <email>`.
9. Confira a limpeza: na Vercel, Settings → Cron Jobs → View Log (a primeira execução
   deve dar 200); no GitHub, aba Actions → "Limpeza de dados vencidos" → **Run workflow**
   (deve terminar em verde; o job só passa com status 200 e resposta "ok"). Se der erro:
   - 401: o `CRON_SECRET` do GitHub difere do da Vercel, ou a Vercel ainda roda um deploy
     anterior à troca do segredo (a função lê o valor do momento do build: faça um novo
     deploy);
   - 404: o `CRON_SECRET` está vazio na Vercel, e a rota fica desligada. Preencha e faça
     um novo deploy;
   - 400: o endereço chamado não está em `ALLOWED_HOSTS` (por exemplo, o Vercel Cron
     chamando pela URL do deploy). Veja o domínio no primeiro log que deu 400 e
     acrescente-o a `ALLOWED_HOSTS`;
   - 301, 302 ou 308: o `SITE_URL` aponta para um endereço que redireciona. Use o
     endereço final, com `https://` e sem barra no fim.
10. Mantenha ligada a proteção dos previews (Deployment Protection, o padrão), mantenha o
    Git Fork Protection ligado e nunca ponha segredo em Preview ou Development.

Trocar o `CRON_SECRET`: mude na Vercel, faça um novo deploy e depois mude no GitHub.
Entre os dois passos, as chamadas de 30 em 30 minutos dão 401; a limpeza volta na
próxima rodada.

Em repositório público, o GitHub desliga os agendamentos depois de 60 dias sem atividade
no repositório (documentação do GitHub, "Events that trigger workflows", evento
`schedule`). Os avisos dos agendamentos, inclusive o de workflow desligado e o de falha,
chegam por e-mail a quem alterou por último a linha `cron` do
`.github/workflows/limpeza.yml`. Essa pessoa precisa reativá-lo: aba Actions →
"Limpeza de dados vencidos" → **Enable workflow**. Até lá, o cron diário da Vercel
continua rodando e um contador pode durar até 2 dias, como a página de privacidade avisa.

**Teste de fumaça** (no domínio de produção):

- `/` e `/healthz` dão 200; o CSS vem com hash no nome; `/privacidade/` mostra o responsável.
- Um anúncio com 3 fotos tiradas do celular salva, e as imagens carregam do R2 sem erro
  de CSP no console do navegador.
- Com JavaScript desligado, uma foto de 3 MB mostra a mensagem do app, não a página da Vercel.
- 6 logins errados dão 429, e de outra rede (4G) o login continua liberado (prova que o
  IP usado é o do visitante).
- `curl -i https://<projeto>.vercel.app/_tarefas/limpeza/` dá 401.
- Nos cabeçalhos aparecem CSP, HSTS (depois do passo 5) e cookies `Secure`.
- `curl -I http://<projeto>.vercel.app/` redireciona para `https://` (não conferido na
  documentação da Vercel; se não redirecionar, defina `SECURE_SSL_REDIRECT=true`).

**Logs da plataforma.** A Vercel registra, por conta própria, cada requisição: caminho,
parâmetros da URL (inclusive o termo buscado), navegador (User-Agent) e IP, e guarda
por 1 hora no Hobby (1 dia no Pro). Isso não pode ser desligado; a página de privacidade
avisa. Quem tem acesso ao painel vê esses registros. O caminho
`/senha/redefinir/<uid>/<token>/` aparece sem máscara ali: hoje não há risco, porque a
recuperação de senha fica desligada sem SMTP, mas se ligar o SMTP, quem vê o painel pode
ver o link por até 1 hora.

**Desistir da Vercel** não exige mudar código: sem `CRON_SECRET` a rota some, as
variáveis novas têm o padrão antigo e o caminho Docker continua igual.

## Organização do código

- `apps/` — regra de negócio: `core` (limite de tentativas, relógio, acesso, erros),
  `accounts` (contas), `catalog` (anúncios; regras puras em `catalog/domain/`),
  `moderation` (aprovação e denúncias), `metrics` (contagens diárias, sem dado do visitante).
- `texts/` — textos de interface que nascem no Python.
- `templates/` e `static/` — apresentação (um CSS único; JS opcional em `static/js/`).
- `config/` — configuração lida do ambiente; `docker/` e `scripts/` — execução e verificação.
- `docs/produto/` — brief, plano, spec e decisões do dono.
