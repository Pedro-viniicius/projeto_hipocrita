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
   Tigris ou Backblaze B2). Em PaaS sem volume, os arquivos somem a cada deploy.
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

## Organização do código

- `apps/` — regra de negócio: `core` (limite de tentativas, relógio, acesso, erros),
  `accounts` (contas), `catalog` (anúncios; regras puras em `catalog/domain/`),
  `moderation` (aprovação e denúncias), `metrics` (contagens diárias, sem dado do visitante).
- `texts/` — textos de interface que nascem no Python.
- `templates/` e `static/` — apresentação (um CSS único; JS opcional em `static/js/`).
- `config/` — configuração lida do ambiente; `docker/` e `scripts/` — execução e verificação.
- `docs/produto/` — brief, plano, spec e decisões do dono.
