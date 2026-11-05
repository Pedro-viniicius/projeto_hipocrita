# Plano técnico: Publicar o "Pão de Cada Dia" na Vercel
- Brief: não há; pedido do lead (dono quer publicar na Vercel). Plano-base: `docs/produto/planos/vitrine-mvp.md`
- Data: 2026-11-05 · Rodada 1
- Documentação da Vercel conferida em 2026-11-05 (links em "Fontes"). O que não foi conferido está marcado como **não verificado**.

## Objetivo e critérios de aceite
Publicar o MVP na Vercel sem perder o que o app já promete (prazos de guarda, IP só em HMAC, fotos sem EXIF, 413 controlado) e manter o caminho Docker do README funcionando.
CA1 — Runtime, entrada WSGI, `vercel.json`, estáticos, migrações e dependências definidos.
CA2 — Banco gerenciado (Neon) com conexões adequadas a serverless e mapeamento de variáveis.
CA3 — Fotos em storage de objetos (recomendação: Cloudflare R2).
CA4 — Upload cabe no limite de corpo, memória e tempo da função; impacto marcado.
CA5 — `cleanup_data` de hora em hora sem expor nada.
CA6 — IP real, logs, HTTPS/HSTS, hosts, `DEMO_DATA`, privacidade e senha tratados.
CA7 — Etapas, passos do dono, lista para `README.md` e `.env.example`.
CA8 — Riscos, custo e comparação com as opções que o README já cobre.

## Resumo para o dono (leia primeiro)
A Vercel **atende**, mas com três custos que a VPS não tem:
1. **Plano pago.** O Hobby é "non-commercial personal use only", e a definição de uso comercial cita "Advertising the sale of a product or service". Uma vitrine de vendas se encaixa nisso. Além disso, no Hobby o cron roda **no máximo 1 vez por dia** ("Expressions like `0 * * * *` ... will fail deployment"), e a página de privacidade promete apagar dados em 24 h. Com o **Pro** (cerca de US$ 20/mês por membro; preço não verificado nesta sessão), as duas coisas se resolvem.
2. **Fotos.** O corpo de qualquer requisição à função tem teto de **4,5 MB** (413 `FUNCTION_PAYLOAD_TOO_LARGE`). Hoje o app aceita 3 fotos de 5 MB (16 MB). Proposta: o navegador reduz as fotos antes do envio (JS) e o servidor passa a aceitar 1 MB por foto. Sem JS, foto de celular acima de 1 MB é recusada.
3. **Logs da plataforma.** A Vercel registra, para cada requisição, caminho, *search params* (o `q` da busca), User-Agent e IP, por 1 h no Hobby e 1 dia no Pro. Isso não pode ser desligado. O texto de privacidade precisa dizer isso.

Na comparação, a VPS (opção recomendada no README) continua mais barata e cumpre tudo sem mudar código (ver "Alternativa").

## Contexto atual
- Entrada WSGI: `config/settings.py:58` `WSGI_APPLICATION = "config.wsgi.application"`; `config/wsgi.py:1-7`. `manage.py` na raiz.
- Python: `pyproject.toml:5` `requires-python = ">=3.14"`, **sem** `dependencies`; dependências só em `requirements.txt:1-8`. A Vercel aceita 3.12 (padrão), 3.13 e **3.14**.
- **Armadilha:** com `pyproject.toml` e `requirements.txt` e sem lockfile, o builder escolhe o pyproject ("Detected both pyproject.toml and requirements.txt but no lockfile; using pyproject.toml", issue vercel/vercel#14041, aberta). Do jeito que o repositório está hoje, o build não instalaria nada.
- Estáticos: `STATIC_ROOT` em `config/settings.py:103`, whitenoise `CompressedManifestStaticFilesStorage` em `config/env.py:76`. A Vercel roda `collectstatic` sozinha quando há `STATIC_ROOT` e serve pela CDN; o whitenoise só atua no `vercel dev`. `staticfiles/` está no `.gitignore:17`.
- Banco: `config/env.py:49-70` lê `POSTGRES_HOST/PORT/DB/USER/PASSWORD` e `DB_CONN_MAX_AGE` (padrão 60), com `CONN_HEALTH_CHECKS` ligado; não lê `DATABASE_URL`. `apps/moderation/services.py:48` usa `.iterator()` fora de transação, o que abre cursor no servidor, e isso quebra no pooler em modo transação.
- Fotos: `config/env.py:73-105` (local ou s3; credenciais do ambiente). O django-storages 1.14.6 lê `AWS_SESSION_TOKEN` do ambiente (`lookup_env(["AWS_SESSION_TOKEN", ...])`). A Vercel avisa que variáveis `AWS_*` "may appear in your Vercel Functions even if you don't set them".
- Limites: `MAX_UPLOAD_MB` padrão 5 (`config/settings.py:111`); teto do corpo `(3 × MB + 1) MiB` (`config/settings.py:115`); 413 próprio em `apps/core/middleware.py:67-96`. As fotos são processadas uma de cada vez (`apps/catalog/photos.py:72-85`), com `draft` no JPEG (`apps/catalog/imaging.py:137-139`). O pico de ~267 MB por foto de 24 MP foi medido pelo lead (não verificado por mim).
- IP: `apps/core/ratelimit.py:46-60` usa o N-ésimo IP da direita do `X-Forwarded-For` quando `TRUSTED_PROXY_HOPS>0`. A Vercel **sobrescreve** o `X-Forwarded-For` com o IP do cliente ("do not forward external IPs ... to prevent IP spoofing"), então `TRUSTED_PROXY_HOPS=1` funciona sem mudar código.
- Limpeza: comando em `apps/core/management/commands/cleanup_data.py:25-51`, idempotente; hoje roda no `docker/start.sh:6` e no cron da VPS (README:113-130).
- Privacidade: `templates/core/privacy.html:42` diz que "os registros do site não guardam IP, o que foi buscado nem links de troca de senha", com a ressalva genérica sobre "o servidor onde o site roda".
- Recuperação de senha: desligada sem SMTP com `DEBUG=false` (`apps/accounts/views.py:190-196`). Continua igual.
- Teste que obriga a documentar toda variável lida em `config/*.py`: `apps/core/tests/test_settings.py:221-233`.

## Abordagens consideradas
**Storage das fotos (CA3)**
| Opção | django-storages | Custo/limites | Contras |
|---|---|---|---|
| **Cloudflare R2** | Sim, como "S3 Compatible" (doc do django-storages) | 10 GB e saída grátis (faixa gratuita; não verificado nesta sessão) | Conta Cloudflare; sem região na América do Sul |
| AWS S3 (sa-east-1) | Sim, nativo | Saída paga; IAM mais trabalhoso | Mais caro e mais configuração para uma pessoa só |
| Vercel Blob | **Não** (o django-storages não tem backend; só SDK/REST) | Cobrança da Vercel | Exige escrever um `Storage` próprio: código novo sem ganho |

**Fotos versus 4,5 MB (CA4)**
| Opção | Prós | Contras | Risco |
|---|---|---|---|
| **A. JS reduz no navegador + `MAX_UPLOAD_MB=1`** | ~60 linhas de JS; o servidor continua validando tudo; envio menor e mais rápido no 4G | Sem JS, foto acima de 1 MB é recusada | Baixo |
| B. Upload direto ao R2 (URL pré-assinada) | Sem limite de corpo | JS obrigatório, CORS, objetos órfãos, o servidor baixa de volta para validar; refaz o fluxo de fotos | Alto |
| C. Uma foto por envio, `MAX_UPLOAD_MB=4` | Sem JS | Muda tela e fluxo (spec); 3 envios por anúncio | Médio |

**Cron (CA5):** no Pro, Vercel Cron de hora em hora. No Hobby, só diário, e teria de ser complementado por um GitHub Actions de hora em hora chamando a mesma rota (etapa 7, condicional). Em repositório público, o GitHub desativa workflows agendados depois de 60 dias sem atividade (não verificado nesta sessão).

**Migrações (CA1):** no script de build do Pro, só com `VERCEL_ENV=production` e pela conexão direta (não pelo pooler). Alternativa descartada: rodar à mão da máquina do dono, que é fácil de esquecer e põe segredo de produção na máquina a cada deploy.

## Decisão
- **Plano Pro**, região `gru1` (São Paulo) e **Neon** `aws-sa-east-1` (São Paulo, GA desde fev/2025), para o banco ficar perto da função e dentro do Brasil. Fotos no **R2**, com o bucket privado e as URLs assinadas que o app já usa.
- **Dependências no `pyproject.toml`** (cópia exata do `requirements.txt`, com um teste que impede divergência), porque é o caminho documentado pela Vercel. O Dockerfile continua usando o `requirements.txt`.
- Entrada explícita `[tool.vercel] entrypoint = "config.wsgi:application"` e build `[tool.vercel.scripts] build = "sh scripts/vercel_build.sh"` (migrate só em produção, mais `check --deploy` no log).
- `vercel.json`: `regions`, `functions["config/wsgi.py"]` (`maxDuration` 60, `excludeFiles` dos testes e docs), `crons` de hora em hora e `ignoreCommand` que pula builds fora de produção. Assim nenhum preview usa o banco real.
- Pooler do Neon com `DB_DISABLE_SERVER_SIDE_CURSORS=true` (recomendação do Django para PgBouncer em modo transação) e `DB_CONN_MAX_AGE=60` com health check (já existe).
- Cron numa rota GET protegida por `CRON_SECRET` (cabeçalho `Authorization: Bearer`), porque é o mecanismo da Vercel. Sem `CRON_SECRET`, a rota dá 404: na VPS nada muda.
- Fotos: opção A.
- Excesso evitado: nada de Vercel Blob, de upload direto, de `DATABASE_URL` (as variáveis do Neon já batem com quatro das cinco que o app lê) nem de pacote novo.

## Esquema e contratos
Sem migração de banco. Contratos novos:
- `GET /_tarefas/limpeza/` (`core:cleanup_cron`): `CRON_SECRET` vazio → 404; cabeçalho diferente de `Bearer <CRON_SECRET>` (comparação `hmac.compare_digest`) → 401; certo → roda `call_command("cleanup_data")` e responde 200 `ok` (`text/plain`, `never_cache`). Outros métodos → 405.
- `settings.CRON_SECRET: str` (lido com `ENV.get("CRON_SECRET", "").strip()`).
- `build_databases`: `"DISABLE_SERVER_SIDE_CURSORS": env_bool(env, "DB_DISABLE_SERVER_SIDE_CURSORS", False)` no dicionário do Postgres.
- `build_storages` (s3): `"security_token": None` nas OPTIONS (credencial estática; ignora o `AWS_SESSION_TOKEN` que a plataforma possa injetar).
- Widget de `photos` ganha `data-max-mb="<MAX_UPLOAD_MB>"`, lido pelo JS.

Mapa de variáveis Neon → app (o nome das injetadas deve ser conferido no painel depois de conectar):
| App lê | Origem na Vercel |
|---|---|
| `POSTGRES_HOST` | `POSTGRES_HOST` do Neon (host **com `-pooler`**; conferir) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Os mesmos nomes, injetados pelo Neon |
| `POSTGRES_DB` | **Manual**: o Neon injeta `POSTGRES_DATABASE`/`PGDATABASE` (ex.: `neondb`), não `POSTGRES_DB` |
| `POSTGRES_PORT` | Padrão 5432 |
| `PGHOST_UNPOOLED` | Injetada pelo Neon; usada só pelo `scripts/vercel_build.sh` no `migrate` |
| `PGSSLMODE=require`, `PGCHANNELBINDING=require` | Manuais; a libpq lê direto (o padrão da string do Neon) |

## Etapas
| # | Etapa | Arquivos | Verificação | Responsável | Grupo | Sensível | CAs |
|---|---|---|---|---|---|---|---|
| 1 | Config para serverless: `DB_DISABLE_SERVER_SIDE_CURSORS` em `build_databases`; `security_token: None` no s3; `CRON_SECRET` em settings; `.env.example` ganha `CRON_SECRET=` e `DB_DISABLE_SERVER_SIDE_CURSORS=false` (com explicação), mais `PGSSLMODE`, `PGCHANNELBINDING` e `PGHOST_UNPOOLED` **só como comentário** (linha `PGSSLMODE=` vazia quebraria a libpq no compose). Testes: padrão false/true, opção chega ao `DATABASES`; com `AWS_SESSION_TOKEN` no ambiente, `S3Storage(**options).security_token is None` (sem rede) | `config/env.py`, `config/settings.py`, `.env.example`, `apps/core/tests/test_env_vercel.py` (novo) | `docker compose run --rm -T web pytest apps/core/tests/test_env_vercel.py apps/core/tests/test_settings.py -q` | dev | A | sim | CA2, CA3, CA5 |
| 2 | Rota `GET /_tarefas/limpeza/` conforme o contrato. Testes: 404 sem segredo; 401 sem cabeçalho, com `Bearer` errado ou sem o prefixo; 200 com o certo, e um `RateLimitCounter` de 25 h some; POST → 405; `Cache-Control` com no-store; o corpo não traz contagens | `apps/core/views.py`, `apps/core/urls.py`, `apps/core/tests/test_cron.py` (novo) | `docker compose run --rm -T web pytest apps/core/tests/test_cron.py apps/core/tests/test_urls.py -q` | dev | B | sim | CA5, CA6 |
| 3 | Fotos reduzidas no navegador: `static/js/fotos.js` no `change` do `input[type=file][data-max-mb]` reduz cada imagem para lado maior ≤ 1280 px, JPEG q0,85, via `createImageBitmap` + canvas (sai sem EXIF), e troca `input.files` com `DataTransfer`; enquanto processa, o botão fica `aria-disabled`; se falhar (ex.: HEIC fora do Safari), mantém o original; se o total passar de `3×MB+1` MiB, mostra aviso e bloqueia o envio. `forms_seller.py:209` põe `data-max-mb` no widget. O template inclui o script. `PHOTOS_HELP` (texto proposto): "Até 3 fotos (JPG, PNG ou WebP). O site reduz as fotos antes de enviar; se não conseguir, cada uma pode ter até {mb} MB." Teste: o formulário renderiza `data-max-mb` igual a `MAX_UPLOAD_MB` | `static/js/fotos.js` (novo), `templates/seller/offer_form.html`, `apps/catalog/forms_seller.py`, `texts/seller.py`, `apps/catalog/tests/test_photos_client_resize.py` (novo) | `docker compose run --rm -T web pytest apps/catalog/tests/test_photos_client_resize.py apps/catalog/tests/test_seller_photos.py -q` e teste manual num celular (3 fotos da câmera) | dev (texto revisado pelo designer) | B | não | CA4 |
| 4 | Texto de privacidade honesto para qualquer hospedagem. Trocar a 2ª frase de `privacy.html:42` por: "A empresa que hospeda o site registra, por conta própria, cada acesso (endereço da página, inclusive o termo buscado, navegador e IP) e apaga esses registros no prazo dela, que é curto (na hospedagem atual, até 1 dia)." Na linha 49, citar "a empresa de hospedagem" entre os lugares onde os dados ficam. **O dono revisa o texto** | `templates/core/privacy.html` | `docker compose run --rm -T web pytest apps/core/tests/test_privacy.py -q` | designer | B | não | CA6 |
| 5 | Arquivos da Vercel: `pyproject.toml` ganha `dependencies` (os mesmos 7 pinos do `requirements.txt`), `[tool.vercel] entrypoint` e `[tool.vercel.scripts] build`; `scripts/vercel_build.sh` (`set -eu`; se `VERCEL_ENV=production`, `POSTGRES_HOST="${PGHOST_UNPOOLED:-$POSTGRES_HOST}" python manage.py migrate --noinput`; depois `python manage.py check --deploy`, que só avisa); `vercel.json` (abaixo); `.vercelignore` com `.env`, `.env.*`, `!.env.example`, `.venv/`, `media/`, `staticfiles/`, `db.sqlite3`, `docs/`, `.claude/`, `.pytest_cache/`, `.ruff_cache/`. Testes: deps do pyproject == linhas do `requirements.txt`; `entrypoint` == `settings.WSGI_APPLICATION` em formato `módulo:nome`; cada `crons[].path` resolve para `core:cleanup_cron`; `.vercelignore` contém `.env*` e `!.env.example`; `vercel.json` é JSON válido | `pyproject.toml`, `vercel.json` (novo), `.vercelignore` (novo), `scripts/vercel_build.sh` (novo), `apps/core/tests/test_deploy_vercel.py` (novo) | `docker compose run --rm -T web sh -n scripts/vercel_build.sh && docker compose run --rm -T web pytest apps/core/tests/test_deploy_vercel.py -q` | dev | C | sim | CA1, CA2, CA5 |
| 6 | Documentação: seção "Vercel" no README e ajustes no `.env.example` (lista abaixo) | `README.md`, `.env.example` | `docker compose run --rm -T web pytest apps/core/tests/test_settings.py -q` (documentação de variáveis) e leitura | dev | C | não | CA7 |
| 7 | **Só se o dono ficar no Hobby:** `vercel.json` passa o cron para diário (`7 6 * * *`) e entra `.github/workflows/limpeza.yml` (`schedule: "7 * * * *"` e `workflow_dispatch`; `curl -fsS -H "Authorization: Bearer ${{ secrets.CRON_SECRET }}" "${{ vars.SITE_URL }}/_tarefas/limpeza/"`; `permissions: {}`) | `.github/workflows/limpeza.yml` (novo), `vercel.json` | `docker compose run --rm -T web pytest apps/core/tests/test_deploy_vercel.py -q` e disparo manual pelo `workflow_dispatch` | dev | D | sim | CA5 |
| 8 | Verificação final | — | `docker compose run --rm -T web scripts/verify.sh` (base: 1017 passaram) | lead | D | — | todos |

`vercel.json` (etapa 5; JSON não aceita comentário):
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "regions": ["gru1"],
  "ignoreCommand": "test \"$VERCEL_ENV\" != production",
  "functions": {
    "config/wsgi.py": {
      "maxDuration": 60,
      "excludeFiles": "{docs/**,apps/**/tests/**,conftest.py,.claude/**}"
    }
  },
  "crons": [{ "path": "/_tarefas/limpeza/", "schedule": "7 * * * *" }]
}
```
- `ignoreCommand` sai com 0 (pula o build) fora de produção. Que o `VERCEL_ENV` existe no Ignored Build Step: não verificado; confirmar no 1º push de outra branch.
- Grupos: A → B (2, 3 e 4 não compartilham arquivos) → C (5 e 6 não compartilham) → D. O `.env.example` aparece na 1 (grupo A) e na 6 (grupo C), em grupos sequenciais.
- **Atenção do lead:** o `qa` trabalha agora em `apps/core/tests/`. As etapas 1, 2 e 5 só **criam** arquivos novos ali. A etapa 1 apenas roda `test_settings.py`, sem editá-lo.

### O que o dono faz nos painéis (depois de aprovar; nada disso foi criado)
1. Escolher o plano (pergunta P1) e importar o repositório `Pedro-viniicius/projeto_hipocrita` na Vercel (Git, branch `main`). O preset Django é detectado.
2. Marketplace → Neon → banco em **AWS São Paulo (`aws-sa-east-1`)**, ligado só ao ambiente Production. No SQL Editor do Neon: `ALTER DATABASE <nome> SET timezone TO 'UTC';` (evita o `SET TIME ZONE` por conexão, que se perde no pooler).
3. Conferir as variáveis injetadas e acrescentar: `POSTGRES_DB=<valor de PGDATABASE>`, `PGSSLMODE=require`, `PGCHANNELBINDING=require`, `DB_DISABLE_SERVER_SIDE_CURSORS=true`.
4. Cloudflare → R2: bucket privado; token de API "Object Read & Write" **restrito a esse bucket**. Na Vercel: `STORAGE_BACKEND=s3`, `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_REGION_NAME=auto`, `AWS_S3_ENDPOINT_URL=https://<conta>.r2.cloudflarestorage.com`.
5. Variáveis do app (Production; as secretas marcadas como **Sensitive**): `SECRET_KEY` (nova; não reaproveitar a de outro ambiente), `ALLOWED_HOSTS=<projeto>.vercel.app`, `CSRF_TRUSTED_ORIGINS=https://<projeto>.vercel.app` (**nunca** `*.vercel.app`), `SECURE_PROXY_SSL_HEADER=true`, `TRUSTED_PROXY_HOPS=1`, `MAX_UPLOAD_MB=1`, `CRON_SECRET` (gerar com `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`), `PRIVACY_CONTROLLER_NAME`, `PRIVACY_CONTACT_EMAIL`. **Não** definir `DEBUG` nem `DEMO_DATA`. Depois de confirmar o HTTPS: `SECURE_HSTS_SECONDS=31536000`.
6. Push em `main`. No log do build, conferir: "Python 3.14", dependências instaladas a partir do pyproject, `migrate` rodou, `collectstatic` rodou e `check --deploy` sem W001.
7. Administrador, sem shell na Vercel: na própria máquina, crie `.env.producao` (já coberto pelo `.gitignore` e pelo `.vercelignore`) com `POSTGRES_HOST=<host sem -pooler>`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PGSSLMODE=require`, `SECRET_KEY` (a mesma da Vercel) e `DEBUG=false`, e rode `docker build -t paodecadadia . && docker run --rm -it --env-file .env.producao paodecadadia python manage.py createsuperuser`. Apague o arquivo no fim. O mesmo vale para `changepassword`.
8. Settings → Cron Jobs → View Log: a primeira execução deve dar 200.
9. Manter o Deployment Protection dos previews ligado (o padrão).

### Teste de fumaça (dono ou lead, no domínio de produção)
`/` e `/healthz` dão 200; o CSS vem com hash; o anúncio com 3 fotos tiradas do celular salva, e as imagens carregam do R2 sem erro de CSP; com JS desligado, uma foto de 3 MB mostra a mensagem do app, não a página da Vercel; 6 logins errados dão 429, e de outra rede (4G) o login continua liberado (prova que o IP é do cliente); `curl -i https://<projeto>.vercel.app/_tarefas/limpeza/` dá 401; nos cabeçalhos aparecem CSP, HSTS e cookies `Secure`; `curl -I http://<projeto>.vercel.app/` redireciona para https (não verificado na doc); `/privacidade/` mostra o responsável.

### Lista para o `README.md` (etapa 6)
- Nova seção "Vercel" com: plano (Pro e o porquê), passos 1 a 9 acima, tabela Neon → app, R2, a tabela de limites (4,5 MB, `MAX_UPLOAD_MB=1`, fotos reduzidas no navegador), migração no build só em produção, previews sem build, cron, administrador via Docker local e logs da plataforma (o que registram e por quanto tempo).
- Em "Limpeza de dados vencidos": "Na Vercel, o `vercel.json` agenda `/_tarefas/limpeza/` de hora em hora (exige `CRON_SECRET`)".
- Em "Publicar", item 4: R2 obrigatório em plataforma sem disco persistente (Vercel).

### Lista para o `.env.example`
- Etapa 1: `CRON_SECRET=` (o que é, como gerar, Sensitive, vazio = rota desligada); `DB_DISABLE_SERVER_SIDE_CURSORS=false` (true com pooler em modo transação, como o do Neon); como comentários, `# PGSSLMODE=require`, `# PGCHANNELBINDING=require` e `# PGHOST_UNPOOLED=` (lida só pelo `scripts/vercel_build.sh`).
- Etapa 6: em `MAX_UPLOAD_MB`, "Na Vercel use 1 (limite de 4,5 MB por requisição)"; em `TRUSTED_PROXY_HOPS`, "Vercel: 1"; em `FORWARDED_ALLOW_IPS` e no bloco do gunicorn, "não se aplicam na Vercel"; em `DB_CONN_MAX_AGE`, que com o pooler 60 serve.

## Pontos para o seguranca
- Etapa 2: comparação em tempo constante; sem segredo, 404; o segredo nunca vai a log nem a resposta; GET sem efeito colateral perigoso (a limpeza é idempotente); avaliar se vale um aviso no `check --deploy` para `CRON_SECRET` com menos de 32 caracteres.
- Etapa 1: `security_token=None` fecha a mistura de credenciais do R2 com o `AWS_SESSION_TOKEN` da plataforma. Conferir que a chave do R2 vale só para o bucket.
- Etapa 5: `.vercelignore` impede que `vercel deploy` pela CLI suba um `.env` local (os arquivos do deploy ficam visíveis na aba Source). O `migrate` usa a conexão direta só no build de produção; os previews não constroem.
- `CSRF_TRUSTED_ORIGINS` sem curinga `*.vercel.app` (qualquer pessoa cria um `*.vercel.app`).
- Logs da Vercel: o caminho `/senha/redefinir/<uid>/<token>/` aparece sem máscara no log da plataforma. Hoje não há risco (a recuperação está desligada sem SMTP), mas se o dono ligar o SMTP, quem tem acesso ao painel pode ver o token por até 1 dia.
- `X-Forwarded-For` sobrescrito pela Vercel (documentado), o que torna `TRUSTED_PROXY_HOPS=1` seguro. Se um dia houver um proxy na frente da Vercel (ex.: Cloudflare com laranja), o valor muda.
- Transferência internacional (LGPD art. 33): a Vercel e a Cloudflare são empresas dos EUA; o R2 não tem região no Brasil. Ver P4.

## Riscos e como reverter
| Risco | Como reverter ou mitigar |
|---|---|
| O build instala dependências erradas (precedência pyproject/requirements) | O teste da etapa 5 mantém os dois iguais; o log do build mostra a origem. Plano B: `.vercelignore` com `pyproject.toml` e `.python-version` com `3.14` |
| `migrate` no build com o código antigo ainda no ar | Migrações aditivas (regra do projeto: destrutiva vai separada); o build que falha não publica. Instant Rollback **não** desfaz o esquema |
| Pooler e Django (cursor no servidor, `SET TIME ZONE`) | `DB_DISABLE_SERVER_SIDE_CURSORS=true` e `ALTER DATABASE ... timezone`; se ainda falhar, `POSTGRES_HOST=<host direto>` e `DB_CONN_MAX_AGE=0` |
| A Vercel não acha o manifest dos estáticos (`{% static %}` dá 500) | A doc diz que o whitenoise com manifest é suportado; testar na 1ª publicação; plano B: `WHITENOISE_USE_FINDERS` |
| Cold start (import do Django + botocore) + Neon suspenso após inatividade | 1 a 3 s na 1ª visita depois de ociosidade (estimativa, não medida); aceitar ou desligar o autosuspend no Neon pago |
| Cron atrasado ou duplicado ("best effort") | `cleanup_data` é idempotente; prazo coberto com folga de horas |
| "Cron Jobs are a legacy feature and will be migrated to Schedules" | O `vercel.json` segue válido; migrar quando a Vercel anunciar |
| Sem JS, foto acima de 1 MB é recusada | Mensagem clara do app até 4 MiB de corpo; acima de 4,5 MB aparece a página crua da Vercel (perde o formulário). Impacto aceito na P2 |
| Desistir da Vercel | Nada do que foi feito quebra o Docker: `CRON_SECRET` vazio desliga a rota, as variáveis novas têm padrão antigo e o JS só ajuda. Voltar para o README/VPS |

Memória e tempo (CA4): Hobby tem 2 GB / 1 vCPU; Pro tem 2 GB padrão e até 4 GB / 2 vCPU. O teto de duração padrão é 300 s; aqui fica em 60 s. As fotos são processadas uma de cada vez, então o pico é de ~267 MB mais o processo, longe dos 2 GB, mesmo se a concorrência dentro da função (beta para Python) juntar três envios. Com a redução no navegador, a foto chega com ≤ 1280 px e o custo de CPU cai a quase nada.

## Alternativa (CA8)
| | Vercel Pro | VPS + Caddy (README) | Fly.io / Railway (README) |
|---|---|---|---|
| Custo mensal | ~US$ 20 + Neon/R2 grátis | ~US$ 4 a 6 (não verificado) | ~US$ 5 a 10 (não verificado) |
| Fotos | 4,5 MB por envio: exige JS + 1 MB | 20 MB no Caddy, sem mudança | Sem limite prático |
| Logs | IP, UA e busca na plataforma (1 dia) | Sob controle do dono (sem IP) | Logs da plataforma (não verificado) |
| Cron de hora em hora | Sim | crontab | Agendador da plataforma |
| Operação | Sem servidor para manter; deploy por push | Atualizar o SO e o Docker | Intermediária |
| Mudança de código | Etapas 1 a 6 | Nenhuma | Nenhuma |

Recomendação do arquiteto: se o motivo da Vercel for só "deploy por push sem servidor", Fly.io ou Railway entregam isso por um quarto do preço, sem mexer no upload e sem logs com IP. Se o dono quer a Vercel mesmo assim, este plano funciona.

## Perguntas em aberto e premissas adotadas
- **P1 (dono):** Pro ou Hobby? Premissa: Pro (cláusula comercial e cron). Se for Hobby, rode a etapa 7 e consulte o suporte da Vercel sobre o uso comercial.
- **P2 (dono):** aceita que, sem JS, a foto tenha no máximo 1 MB? Premissa: sim.
- **P3 (dono):** aprova o novo texto de privacidade (etapa 4)?
- **P4 (dono):** aceita dados processados por empresas dos EUA (Vercel, Cloudflare)? Premissa: sim, com banco e função em São Paulo. Se não, o R2 vira AWS S3 `sa-east-1` (mesmo código; muda só o endpoint).
- Premissa: domínio `*.vercel.app` no início; um domínio próprio entra em `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`.
- Premissa: a Vercel lê `requires-python` e escolhe 3.14 (a doc diz que sim; confirmar no log).

## ADR
**ADR-002 — Publicação na Vercel (2026-11-05).** Contexto: o dono pediu a Vercel; o app nasceu para container. Decisão: função Python na Vercel Pro (`gru1`), Neon (`aws-sa-east-1`) com pooler, R2 com URLs assinadas, migração no build de produção, limpeza por Vercel Cron numa rota com `CRON_SECRET` e fotos reduzidas no navegador com `MAX_UPLOAD_MB=1`. As dependências passam a existir também no `pyproject.toml`, com um teste de igualdade. Consequências: custo fixo maior que o da VPS; limite de foto sem JS; logs de acesso com IP na plataforma, que a página de privacidade passa a declarar; o Docker continua como caminho alternativo e sem regressão.

## Fontes
- Python runtime: https://vercel.com/docs/functions/runtimes/python · versão: https://vercel.com/docs/functions/runtimes/python/python-version
- Django: https://vercel.com/docs/frameworks/full-stack/django · limites: https://vercel.com/docs/functions/limitations
- Cron: https://vercel.com/docs/cron-jobs/usage-and-pricing · https://vercel.com/docs/cron-jobs/manage-cron-jobs
- Cabeçalhos: https://vercel.com/docs/headers/request-headers · logs: https://vercel.com/docs/logs/runtime
- Uso justo/comercial: https://vercel.com/docs/limits/fair-use-guidelines · variáveis reservadas: https://vercel.com/docs/environment-variables/reserved-environment-variables
- Precedência pyproject: https://github.com/vercel/vercel/issues/14041 · Neon São Paulo: https://neon.com/docs/changelog/2025-02-28 · django-storages: https://django-storages.readthedocs.io/en/latest/
