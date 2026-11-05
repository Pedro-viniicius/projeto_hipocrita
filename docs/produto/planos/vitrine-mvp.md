# Plano técnico: Vitrine "Pão de Cada Dia" (MVP)
- Brief: docs/produto/briefs/vitrine-mvp.md
- Spec de telas (em paralelo, do `designer`): docs/produto/specs/vitrine-mvp.md
- Decisões do dono: docs/produto/decisoes.md
- Data: 2026-11-05 · Rodada 1

> Tamanho: passa das 250 linhas porque é o primeiro plano (stack, estrutura e texto do CLAUDE.md). A feature não precisa virar duas entregas: o dono pediu entrega de ponta a ponta e há ordem de corte (seção "Corte de escopo").

## Objetivo e critérios de aceite
Entregar a vitrine pública, a área do vendedor e a administração mínima descritas no brief, com dados persistidos, subindo com `docker compose up`. Os CAs são os do brief, sem renumerar: **CA1 a CA20** (`docs/produto/briefs/vitrine-mvp.md:187-206`). A matriz CA → etapa → teste está em "Testes".

## Contexto atual
- Projeto vazio: sem git, sem código. Existem só `CLAUDE.md`, `.claude/agents/*.md` e `docs/produto/`.
- `CLAUDE.md:3-12`: "Contexto do projeto" a definir; este plano propõe o texto (seção final).
- `docs/produto/decisoes.md`: fuso `America/Sao_Paulo`, cadastro aberto com aprovação do 1º anúncio, 5 categorias editáveis, reconfirmação de venda pontual em 14 dias, identidade visual; suposições do lead: **anúncio sem WhatsApp autorizado não fica público**, recuperação de senha preparada com e-mail no console, página "Privacidade", fotos de até 5 MB (3 por anúncio).
- Spec do designer (lida em 2026-11-05, ainda em escrita): rotas sugeridas (`spec:17`), parâmetros `q`, `cat`, `hoje`, `pagina` com 20 cartões cumulativos (`spec:215-221`), âncora `#oferta-<id>`, contato por redirecionamento `GET /oferta/<id>/whatsapp` (`spec:226`), estados (`spec:153-166`), formulário com fotos no mesmo envio (`spec:263-282`), fontes em `static/fontes/`, sprite `static/icones.svg`. Este plano adota esses nomes. Divergências estão em "Decisões e suposições" (D14, D19 a D22).
- Ferramentas: Docker 29.8 + Compose v5.5.1 e Python 3.14.4 conferidos com `--version`; Node 22/pnpm e google-chrome: informados pelo lead, não verificados.

## Abordagens consideradas
| Abordagem | Prós | Contras | Risco |
|---|---|---|---|
| **Django 5.2 LTS + PostgreSQL 17**, templates no servidor | CSRF, sessões em cookie HttpOnly, forms que reexibem dados, migrações, hash de senha e i18n pt-BR prontos; suporte LTS até abr/2028; um processo só | Python no container; serviço de mídia local por view própria | Baixo |
| Node SSR (Express/Fastify + Nunjucks, ou Next.js) | Node já na máquina | CSRF, sessão, validação, migrações e upload montados com 5 ou 6 libs; Next puxa JS no cliente e não ajuda o "funciona sem JS" | Médio: mais código de infraestrutura para uma pessoa manter |
| Rails / Laravel | Também têm tudo pronto | Ruby e PHP não estão na máquina, e o time de agentes não tem padrão neles | Médio |

## Decisão
**Django 5.2 LTS (5.2.19) + PostgreSQL 17, renderização no servidor, um container web + um de banco.** Django entrega de fábrica o que o brief exige e que mais custa fazer à mão: proteção CSRF em todo formulário, sessão em cookie HttpOnly, formulários que reexibem o que foi digitado com o erro ao lado do campo, migrações versionadas, hash de senha e mensagens de validação já em pt-BR. Com isso o código do projeto fica concentrado em regras de negócio. A LTS, em vez da 6.x, reduz upgrades para quem mantém sozinho. PostgreSQL é o relacional padrão nas plataformas baratas (Fly, Railway, Neon, VPS). O código não usa recurso exclusivo do Postgres, e por isso a suíte também roda fora do Docker com SQLite. Fica de fora: Redis, Celery, filas e build de front-end. O CSS é um arquivo só e o JS são três scripts opcionais.

Bibliotecas (versões conferidas no PyPI em 2026-11-05):
| Pacote | Versão | Para quê |
|---|---|---|
| Django | 5.2.19 | framework (suporta Python 3.10 a 3.14) |
| psycopg[binary] | 3.3.8 | driver Postgres (wheels cp314) |
| Pillow | 13.0.0 | **tipo real do arquivo** (decodifica o conteúdo; aceita só `JPEG`/`PNG`/`WEBP` em `img.format`), corrige rotação EXIF, remove metadados (inclusive GPS) e gera 2 tamanhos em WebP |
| gunicorn | 26.2.0 | servidor em produção |
| whitenoise | 6.12.0 | serve `static/` com hash e compressão, sem nginx |
| django-storages | 1.14.6 | S3 quando `STORAGE_BACKEND=s3` (classifiers vão até Django 5.1; compatibilidade com 5.2 **não verificada**, é amplamente usado) |
| boto3 | 1.43.124 | cliente S3 do django-storages |
| pytest / pytest-django | 9.2.0 / 4.14.0 | testes (só dev) |
| time-machine | 3.6.0 | relógio controlado em testes de view (só dev) |
| ruff | 0.17.3 | lint e formatação (só dev) |

Descartadas: `python-magic`/`filetype`, porque o Pillow já valida o conteúdo e o libmagic exigiria pacote no sistema; `pillow-heif`, porque o iOS converte HEIC para JPEG quando o `accept` não inclui HEIC (suposição D8); `django-ratelimit` 4.1.0, porque exige memcached ou Redis e recusa DatabaseCache com o erro E003 (conferido em `django_ratelimit/checks.py`). No lugar dele entra um limitador próprio de cerca de 50 linhas sobre o Postgres. `argon2-cffi` também fica de fora: o PBKDF2 padrão basta.

Imagens Docker: `python:3.14-slim` (mesma versão do host) e `postgres:17-alpine` (tags conferidas no Docker Hub).

## Estrutura de pastas
```
compose.yaml  compose.prod.yaml  Dockerfile  .dockerignore  .gitignore  .env.example  README.md
pyproject.toml (pytest + ruff)  requirements.txt  requirements-dev.txt  manage.py  conftest.py
docker/   entrypoint.sh  start.sh (migrate + gunicorn)  start-dev.sh (migrate + load_demo + runserver)  gunicorn.conf.py
scripts/  verify.sh                      # ruff + check + makemigrations --check + check --deploy + pytest
config/   settings.py  settings_test.py  urls.py  wsgi.py
apps/     ── REGRA DE NEGÓCIO (designer não toca) ──
  core/        clock.py ratelimit.py text.py auth.py forms.py middleware.py views.py urls.py testing.py models.py(RateLimitCounter)
  accounts/    models.py(User) phone.py forms.py views.py urls.py
  catalog/     models.py  domain/{availability,states,actions,ordering,search,pricing,whatsapp}.py
               imaging.py photos.py selectors.py presenters.py services_seller.py forms_seller.py
               views_public.py views_seller.py urls_public.py urls_seller.py signals.py
               templatetags/catalog_ui.py  management/commands/load_demo.py
  moderation/  models.py(Report) services.py forms.py forms_public.py views.py views_public.py urls.py urls_public.py
  metrics/     models.py recording.py views.py urls.py
  */migrations/  */tests/
texts/    ── TEXTOS DE INTERFACE que nascem no Python (designer pode editar o texto) ──
  common.py states.py accounts.py seller.py moderation.py public.py
templates/ ── APRESENTAÇÃO ──
  base.html  components/  django/forms/field.html  errors/{403,404,429,500}.html  core/{styleguide,privacy}.html
  accounts/  seller/  public/  moderation/  metrics/
static/   css/app.css  fontes/*.woff2 + OFL.txt  icones.svg  logo.svg  favicon.svg  img/placeholder.svg
          js/  share.js  offer-form.js  enhance.js   # comportamento: dono é o dev
```
- **Pastas de regra de negócio (designer não toca):** `apps/`, `config/`, `docker/`, `scripts/`, `conftest.py`, `requirements*.txt`, `pyproject.toml`, `compose*.yaml`, `Dockerfile`, `static/js/`.
- **Camada do designer:** `templates/`, `static/` (menos `static/js/`) e o texto das constantes em `texts/`, sem mudar nomes de constantes.
- **Onde fica cada texto:** o que nasce no Python (rótulos, dicas e erros de formulário, mensagens de feedback, rótulos de estado, mensagem do WhatsApp) fica em `texts/<área>.py`, como constantes em MAIÚSCULAS. O texto fixo de página fica no template. A spec pede "um arquivo único" (`spec:615`). Aqui é uma pasta única com um módulo por área, para que etapas paralelas não editem o mesmo arquivo.
- **Fontes self-hosted:** `static/fontes/` com `barlow-condensed-{500,600,700}.woff2`, `source-sans-3-{400,600,700}.woff2` e `OFL.txt`. Origem: subset "latin" do Fontsource, que já cobre U+0000-00FF e dispensa o `pyftsubset` (`https://cdn.jsdelivr.net/npm/@fontsource/barlow-condensed@5.3.0/files/barlow-condensed-latin-600-normal.woff2`; o mesmo padrão vale para `@fontsource/source-sans-3@5.3.1`; licença OFL-1.1 conferida no npm).

## Esquema e contratos
Migrações: `0001_initial` por app, geradas na etapa 1. Os dados iniciais vão em `catalog/0002_seed_categories` (migração de dados reversível). Toda tabela tem `id bigint` como chave primária. Datas e horas ficam em `timestamptz` (UTC); "hoje" e "agora" são calculados em `settings.COMMUNITY_TZ`.

| Tabela | Campos (tipo) |
|---|---|
| accounts.User | email varchar(254) único, guardado em minúsculas, `USERNAME_FIELD`; password; is_active; is_staff (= administrador); date_joined; last_login |
| catalog.Category | name varchar(40) único; slug varchar(50) único; position smallint; is_active bool; is_food bool (semente: Comidas e doces = sim, Bebidas = sim) |
| catalog.Seller | user 1:1 CASCADE; display_name varchar(60); slug varchar(70) único; bio varchar(280); service_area varchar(120); hours varchar(120); whatsapp_number varchar(13) (`55DDNNNNNNNNN`, ou vazio); whatsapp_public bool default False; whatsapp_public_changed_at timestamptz null; is_trusted bool (1º anúncio já aprovado); is_demo bool; created_at |
| catalog.Offer | seller FK CASCADE; category FK PROTECT; kind varchar(10) `recurring\|daily\|one_off`; title varchar(80); description varchar(300) em branco permitido; price_cents integer CHECK ≥ 0, ≤ 10.000.000; fulfillment varchar(100) (retirada/entrega); portion varchar(80), ingredients varchar(500), allergens varchar(200), em branco permitido; status varchar(10) `active\|paused\|sold_out\|sold`; status_changed_at timestamptz; approval varchar(10) `pending\|approved`; approved_at null; hidden_at null; hidden_reason varchar(200); daily_confirmed_on date null; closing_time time null; last_confirmed_at timestamptz; created_at; updated_at. Índices: (approval, status), seller |
| catalog.OfferVariant | offer FK CASCADE; name varchar(60); price_cents integer CHECK ≥ 0; position smallint; único (offer, name); no máximo 5 |
| catalog.OfferPhoto | offer FK CASCADE; position smallint 0-2, único (offer, position); card_image e page_image (FileField, nome `offers/<uuid4>-card.webp` / `-page.webp`); page_width e page_height smallint; created_at. Ao apagar a linha, `signals.py` remove os arquivos com `transaction.on_commit` |
| moderation.Report | offer FK CASCADE; reason varchar(20) `misleading\|prohibited\|offensive\|unavailable\|other`; details varchar(500); status `open\|resolved`; created_at; resolved_at null; resolved_by FK User SET_NULL. **Sem IP nem identificação de quem denuncia** |
| metrics.DailyOfferStat | date date; offer FK CASCADE; views int; whatsapp_clicks int; único (date, offer) |
| metrics.DailySearchMiss | date date; term varchar(60), normalizado; count int; único (date, term) |
| core.RateLimitCounter | scope varchar(20); key_hash char(64) (HMAC-SHA256 do IP ou do e-mail com `SECRET_KEY`; nunca o valor puro); window_start timestamptz; count int; único (scope, key_hash, window_start); linhas com mais de 24 h são apagadas a cada gravação |

**Funções puras** (`apps/catalog/domain/`; não importam ORM, recebem `now` e `tz`; `offer` é qualquer objeto com os atributos do modelo):
```python
# availability.py
def daily_expires_at(confirmed_on: date, closing_time: time | None, tz: ZoneInfo) -> datetime
    # combine(confirmed_on, min(closing_time or 23:59, 23:59), tz)
def is_available_today(confirmed_on: date | None, closing_time: time | None, now: datetime, tz: ZoneInfo) -> bool
    # confirmed_on == now.astimezone(tz).date() and now < daily_expires_at(...)  (CA9)
def needs_reconfirmation(last_confirmed_at: datetime, now: datetime, days: int) -> bool   # now - last >= days (CA10)
def has_public_contact(seller) -> bool        # is_demo or (whatsapp_public and whatsapp_number)
def is_page_visible(offer, now, tz, days) -> bool   # aprovado, não oculto, conta ativa, contato público,
                                                    # status != paused, one_off não vencido
def is_listed(offer, now, tz, days) -> bool   # page_visible e (status != sold ou vendido hoje no fuso)
def can_contact(offer, now, tz, days) -> bool # page_visible e status == active
# states.py
class PublicState(StrEnum): AVAILABLE_TODAY, ON_ORDER, SOLD_OUT, SOLD, NONE
class SellerState(StrEnum): PENDING_APPROVAL, HIDDEN, PAUSED, NEEDS_CONFIRMATION  (+ os públicos)
def public_state(offer, now, tz) -> PublicState
    # sold→SOLD; sold_out→SOLD_OUT; recurring|daily confirmado e válido→AVAILABLE_TODAY;
    # recurring→ON_ORDER; resto→NONE (sem selo, spec:166)
def seller_state(offer, now, tz, days) -> SellerState   # hidden > pending > paused > needs_confirmation > público
def state_vm(state) -> StateVM(key, label, icon)        # rótulo e ícone vêm de texts/states.py
# actions.py
ACTIONS = {"pause","resume","sold_out","restock","sold","unsold","confirm_today","reconfirm"}
def allowed_actions(offer, now, tz, days) -> list[str]
def apply_action(offer, action, now, tz, closing_time=None) -> None   # muda atributos; levanta ActionNotAllowed
    # confirm_today: kind in (recurring, daily); status → active; daily_confirmed_on = hoje;
    #   recusa se closing_time <= agora local. reconfirm/resume/unsold de one_off: last_confirmed_at = now
# search.py
def normalize(text: str) -> str                 # casefold + sem acento (NFKD) + espaços colapsados
def split_terms(q: str) -> list[str]            # até 6 termos de 2+ caracteres; q truncado em 80
def match_tier(terms, title, seller_name, body) -> int | None   # 0 título, 1 título+vendedor, 2 com descrição,
                                                                # variações e categoria; None se não casa
# ordering.py
def shuffle_key(day: date, offer_id: int) -> str   # sha256(f"{day.isoformat()}:{offer_id}").hexdigest()
def order_offers(items: list[tuple[int | None, Offer]], day: date) -> list[Offer]   # ordena por (tier, shuffle_key) (CA17)
# pricing.py
def format_brl(cents: int) -> str               # 1250 → "R$ 12,50"; 125000 → "R$ 1.250,00"; sem locale do SO
def parse_brl(raw: str) -> int                  # "8,5"/"8,50"/"R$ 8,50"/"8.50" → 850; ValueError se inválido ou negativo
def display_price(base_cents: int, variant_cents: list[int]) -> tuple[int, bool]   # (centavos, é "A partir de")
# whatsapp.py
def build_message(title: str, variant: str | None, offer_url: str) -> str   # modelo em texts/public.py
def build_whatsapp_url(number: str, message: str) -> str   # f"https://wa.me/{number}?text={quote(message, safe='')}"
```
- `apps/accounts/phone.py`: `normalize_br_mobile(raw: str) -> str | None`. Tira o que não é dígito, o prefixo `55` (quando sobram 12 ou 13 dígitos) e o `0` de tronco. Exige DDD válido entre os 67 DDDs (lista fixa no módulo) e número de 9 dígitos começando com 9. Devolve `55DD9XXXXXXXX`. `format_br_mobile("5535912345678") -> "(35) 91234-5678"`.
- `apps/catalog/imaging.py`: `validate_image(f: UploadedFile) -> None` (tamanho ≤ `MAX_UPLOAD_MB`; `Image.open` + `verify()`; formato em {JPEG, PNG, WEBP}; até 40 MP) e `process_image(f) -> Processed(card: ContentFile, page: ContentFile, width, height)`. O card é 480×480 com corte central e a page tem lado maior de até 1280; os dois saem em WebP com qualidade 80 e sem EXIF.
- `apps/catalog/photos.py`: `save_offer_photos(offer, files: list[UploadedFile], remove_ids: list[int]) -> None`. Usa `select_for_update` no offer; remove só fotos com `offer_id == offer.pk`, recusa se passar de 3 e grava pelo `default_storage`.
- `apps/core/ratelimit.py`: `client_key(request) -> str` (HMAC do IP; usa `X-Forwarded-For` só se `TRUSTED_PROXY_HOPS > 0`), `is_blocked(scope, key, limit, window_s, now=None) -> bool`, `register(scope, key, window_s, now=None)` e o decorador `rate_limited(scope, limit, window_s, key="ip"|"user", methods=("POST",))`, que responde 429 com `errors/429.html`. Limites: login 5 falhas/15 min por IP e por e-mail; cadastro 5/h por IP; denúncia 5/h por IP; envio de fotos 20 arquivos/h por usuário; recuperação de senha 5/h por IP.
- `apps/core/clock.py`: `now() -> datetime` (`timezone.now()`) e `community_tz() -> ZoneInfo`. As views usam só isso, e os testes de view controlam o relógio com `time_machine.travel`.
- `apps/catalog/presenters.py`: `OfferCardVM(anchor_id, url, title, photo_url|None, photo_w, photo_h, price_label, price_from: bool, price_struck: bool, state: StateVM|None, seller_name, fulfillment, eager: bool)`. Contrato do componente `templates/components/offer_card.html`: o designer usa só esses campos.
- `apps/core/forms.py`: `BoundField` acessível, que põe `aria-invalid` e `aria-describedby` apontando para dica e erro. O Django 5.2 aceita `bound_field_class` no form e no renderer (**não verificado**: o dev confere na doc da 5.2). `FORM_RENDERER` usa `TemplatesSetting`, o que exige `django.forms` em `INSTALLED_APPS`.

## Rotas e autorização
| Rota | Nome | Acesso |
|---|---|---|
| `/` (GET `q`, `cat`, `hoje=1`, `pagina`) | catalog:home | público |
| `/oferta/<int:pk>/` (os mesmos parâmetros, para o link "Voltar") | catalog:offer_detail | público; 404 se `not is_page_visible` |
| `/oferta/<int:pk>/whatsapp/?variacao=<id>` | catalog:offer_whatsapp | público; conta o clique e responde 302 para wa.me; 404 se `not can_contact`; demo responde 200 com `public/demo_contact.html` |
| `/oferta/<int:pk>/denunciar/` e `.../enviada/` | report:create, report:done | público, POST limitado |
| `/vendedor/<slug>/` | catalog:seller_detail | público; 404 se conta inativa ou sem contato público |
| `/privacidade/`, `/robots.txt`, `/healthz`, `/media/<path>` (só storage local), `/_estilos/` (só DEBUG) | core:* | público |
| `/cadastrar/`, `/entrar/`, `/sair/` (POST) | accounts:signup/login/logout | público |
| `/senha/recuperar/`, `.../enviado/`, `/senha/redefinir/<uidb64>/<token>/`, `/senha/redefinida/` | accounts:password_reset* | público (e-mail no console) |
| `/perfil/senha/`, `/perfil/excluir-conta/` | accounts:password_change, accounts:delete | login |
| `/meus-anuncios/`, `/meus-anuncios/novo/`, `/meus-anuncios/<pk>/editar/`, `/meus-anuncios/<pk>/acao/` (POST `acao`) | seller:dashboard/offer_create/offer_edit/offer_action | login + Seller |
| `/perfil/` | seller:profile | login + Seller |
| `/admin/` (aprovações), `/admin/anuncios/`, `/admin/anuncios/<pk>/` (prévia), `.../aprovar/`, `.../ocultar/`, `.../mostrar/` (POST), `/admin/denuncias/`, `/admin/denuncias/<pk>/tratar/` (POST), `/admin/categorias/`, `/admin/categorias/<pk>/` (POST) | moderation:* | `is_staff` |
| `/admin/metricas/` | metrics:dashboard | `is_staff` |

Autorização no servidor (CA11):
1. Toda view de vendedor busca o anúncio com `get_object_or_404(Offer, pk=pk, seller__user=request.user)`, num helper único em `services_seller.get_own_offer`. Anúncio de outro vendedor dá **404** e nada é gravado.
2. A remoção de fotos filtra por `offer` dentro de `save_offer_photos`.
3. Toda mutação é `@require_POST` e passa pelo CSRF do Django.
4. `apps/core/auth.py` tem `seller_required`, que redireciona anônimo para `/entrar/`, e `staff_required`, que redireciona anônimo e dá 403 para usuário logado sem `is_staff`.
5. O Django admin **não** é instalado; `/admin/` é a área própria.
6. O número de WhatsApp nunca vai para HTML: aparece só no `Location` do 302 (CA6).

## Etapas
Grupos: **A** → **B** (2, 3 e V1 em paralelo) → **C** (4, 5 e 6 em paralelo) → **D** (V2). Na etapa 1, as rotas de todas as etapas ficam congeladas em arquivos `urls*.py` que apontam para views stub com resposta 501. Os stubs de `imaging.py` e `photos.py` também nascem ali, com as assinaturas acima. Depois disso, cada etapa só preenche os próprios módulos. Mudar `urls*.py`, `models.py`, `settings.py` ou `conftest.py` depois da etapa 1 passa pelo lead, entre grupos.

Comando base: `docker compose run --rm web pytest <arquivos> -q`. A verificação completa de cada etapa é `docker compose run --rm web scripts/verify.sh`.

| # | Etapa | Arquivos | Verificação | Resp. | Grupo | Sensível | CAs |
|---|---|---|---|---|---|---|---|
| 1 | **Fundação.** Docker e Compose (db com healthcheck, web com `start-dev.sh`); settings lidas do ambiente (SQLite quando `POSTGRES_HOST` está vazio, `STORAGES` por `STORAGE_BACKEND`, `COMMUNITY_TZ`, cookies `HttpOnly`/`SameSite=Lax`/`Secure` fora do DEBUG, `LANGUAGE_CODE=pt-br`, middleware de CSP com `form-action 'self' https://wa.me https://api.whatsapp.com`, gunicorn sem IP nem query no log); todos os modelos, migrações e a semente das 5 categorias; `core/` (clock, ratelimit e o modelo dele, text com `unique_slug`, auth, forms, healthz, robots, servir mídia, styleguide com VMs de exemplo, error handlers, `testing.py` com helpers de HTML acessível); `urls*.py` completos com stubs 501; stubs de imaging, photos e load_demo; `templates/base.html` mínimo; `static/css/app.css` vazio; `.env.example` com todas as variáveis; README (rodar local, criar admin com `createsuperuser`, publicar em VPS, Fly e Railway) | os da raiz e de `docker/`, `scripts/`, `config/`; `apps/*/{__init__,apps,models,urls*,views*}.py`; `apps/*/migrations/0001_initial.py`; `apps/catalog/migrations/0002_seed_categories.py`; `apps/core/*` (lista acima); `apps/catalog/{signals,imaging,photos}.py` (stubs); `apps/catalog/management/commands/load_demo.py` (stub); `texts/__init__.py`, `texts/common.py`; placeholders mínimos de `templates/base.html`, `templates/core/{styleguide,privacy}.html`, `templates/errors/{403,404,429,500}.html` (depois são do designer); `static/css/app.css` vazio; testes: `apps/core/tests/test_{settings,ratelimit,text,urls,healthz}.py`, `apps/catalog/tests/test_models.py` e `tests/__init__.py` em todos os apps | `docker compose build && docker compose run --rm web scripts/verify.sh && docker compose up -d && curl -fsS localhost:8000/healthz && docker compose down` | dev | A | **sim** (sessão, cookies, segredos, migração, ratelimit) | CA14, CA16 (modelo), CA19 |
| 2 | **Domínio puro e demo.** Funções de `domain/` como no contrato; filtro `brl`; `texts/states.py`; `load_demo` (só roda com `DEMO_DATA=true` e, sem ela, sai com código ≠ 0; idempotente; vendedores e títulos com "(exemplo)", e-mails `@exemplo.invalid`, senha inutilizável, sem número de WhatsApp, `is_demo=True`; cobre todos os tipos e estados, com alimento com e sem ingredientes e oferta do dia confirmada até 18:00) | `apps/catalog/domain/*.py`, `apps/catalog/templatetags/{__init__,catalog_ui}.py`, `apps/catalog/management/commands/load_demo.py`, `texts/states.py`, `apps/catalog/tests/test_{availability,states,actions,search,ordering,pricing,whatsapp_url,load_demo}.py` | `docker compose run --rm web pytest apps/catalog/tests/test_availability.py apps/catalog/tests/test_states.py apps/catalog/tests/test_actions.py apps/catalog/tests/test_search.py apps/catalog/tests/test_ordering.py apps/catalog/tests/test_pricing.py apps/catalog/tests/test_whatsapp_url.py apps/catalog/tests/test_load_demo.py -q` | dev | B | não | CA9, CA10, CA17, CA18; base de CA1, CA3 e CA7 |
| 3 | **Contas e entradas sensíveis.** `phone.py`; cadastro (nome ou marca, e-mail, senha, WhatsApp, autorização desmarcada; cria User e Seller com `unique_slug`; limite por IP); login por e-mail com limite e mensagem genérica; logout por POST; troca e recuperação de senha (e-mail no console); exclusão de conta com senha (transação, `user.delete()` em cascata, logout, mensagem); `imaging.py` real | `apps/accounts/{phone,forms,views}.py`, `apps/catalog/imaging.py`, `texts/accounts.py`, `static/js/enhance.js` (foco no `main`, "Salvando…", mostrar senha; opcional), `templates/accounts/*.html`, `apps/accounts/tests/test_{phone,signup,login,password,account_delete}.py`, `apps/catalog/tests/test_imaging.py` | `docker compose run --rm web pytest apps/accounts apps/catalog/tests/test_imaging.py -q` | dev | B | **sim** (autenticação, upload, dado pessoal) | CA6 (cadastro e validação), CA8 (cadastro), CA13 (validação e tamanhos), CA14 (login), CA15 |
| 4 | **Área do vendedor.** Perfil (dados, WhatsApp validado, autorização revogável, link público); "Meus anúncios" com `seller_state`, `allowed_actions` e aviso de contato não liberado ou de aprovação pendente; formulário de anúncio (tipo, título, categoria, preço `parse_brl`, descrição, retirada, 5 linhas de variação, fotos múltiplas + "Remover esta foto", horário de encerramento e "Já confirmar hoje" para oferta do dia, bloco de alimento quando `category.is_food`); o servidor limpa os campos que não valem para o tipo; aprovação inicial `approved` se `seller.is_trusted`, senão `pending`; editar uma venda pontual renova `last_confirmed_at`; fotos via `photos.py`, com limite por usuário; ações por POST com mensagem e redirecionamento para `#anuncio-<id>`; `offer-form.js` (esconde seções que não valem; opcional) | `apps/catalog/{views_seller,forms_seller,services_seller,photos}.py`, `texts/seller.py`, `templates/seller/{dashboard,profile,offer_form}.html`, `static/js/offer-form.js`, `apps/catalog/tests/test_seller_{profile,offers,actions,authz,photos}.py` | `docker compose run --rm web pytest apps/catalog/tests/test_seller_profile.py apps/catalog/tests/test_seller_offers.py apps/catalog/tests/test_seller_actions.py apps/catalog/tests/test_seller_authz.py apps/catalog/tests/test_seller_photos.py -q` | dev | C | **sim** (autorização, upload, dado pessoal) | CA6, CA7, CA8, CA10, CA11, CA12 (pendente), CA13, CA14 (upload) |
| 5 | **Administração e métricas (leitura).** Aprovar (aprova o anúncio e marca `seller.is_trusted`), ocultar ou mostrar com motivo, lista e busca de anúncios, prévia simples do pendente, denúncias (abertas primeiro, tratar, ocultar), categorias (criar, renomear, posição, `is_active`, `is_food`; sem excluir), métricas em tabelas dos últimos 30 dias (visualizações e cliques por oferta; buscas sem resultado por termo) | `apps/moderation/{services,forms,views}.py`, `apps/metrics/views.py`, `texts/moderation.py`, `templates/moderation/*.html`, `templates/metrics/dashboard.html`, `apps/moderation/tests/test_{admin_access,approvals,reports_admin,categories_admin}.py`, `apps/metrics/tests/test_dashboard.py` | `docker compose run --rm web pytest apps/moderation/tests/test_admin_access.py apps/moderation/tests/test_approvals.py apps/moderation/tests/test_reports_admin.py apps/moderation/tests/test_categories_admin.py apps/metrics/tests/test_dashboard.py -q` | dev | C | **sim** (autorização de admin) | CA12, CA16 (leitura) |
| 6 | **Vitrine pública e contato.** `selectors.public_candidates()` (filtro no banco: aprovado, não oculto, conta ativa, contato público, status ≠ paused, categoria) e depois o Python aplica disponibilidade, busca e rodízio com `now` e `tz`, com páginas cumulativas de 20; `presenters` com cards e links que levam `q/cat/hoje/pagina` e `#oferta-<id>`; página da oferta (variações num GET para `/whatsapp/`, aviso de contato, bloco de alimento com "Não informado pelo vendedor", "Voltar" montado só com os 4 parâmetros); redirecionamento para o WhatsApp; página do vendedor com o endereço em `<input readonly>` e `share.js`; denúncia pública com limite; `metrics/recording.py` (incrementos atômicos com `F()`; não conta HEAD, o próprio vendedor nem User-Agent de robô ou de prévia de link, como `WhatsApp/`, `bot`, `crawl`, `spider`, `preview`); busca sem resultado grava o termo normalizado | `apps/catalog/{views_public,selectors,presenters}.py`, `apps/metrics/recording.py`, `apps/moderation/{views_public,forms_public}.py`, `texts/public.py`, `templates/public/*.html`, `static/js/share.js`, `apps/catalog/tests/test_{home,offer_detail,whatsapp_redirect,seller_page,public_a11y}.py`, `apps/moderation/tests/test_report_public.py`, `apps/metrics/tests/test_recording.py` | `docker compose run --rm web pytest apps/catalog/tests/test_home.py apps/catalog/tests/test_offer_detail.py apps/catalog/tests/test_whatsapp_redirect.py apps/catalog/tests/test_seller_page.py apps/catalog/tests/test_public_a11y.py apps/moderation/tests/test_report_public.py apps/metrics/tests/test_recording.py -q` | dev | C | **sim** (entrada pública, contato) | CA1, CA2, CA3, CA4, CA5, CA6 (sem número no HTML), CA12 (denúncia), CA14 (denúncia), CA16, CA17, CA20 (checagens automáticas) |

**Camada visual (designer), fora do limite de 6 etapas do dev:**
| # | Trabalho | Arquivos | Verificação | Grupo |
|---|---|---|---|---|
| V1 | Tokens, `@font-face`, base e componentes da spec; fontes, sprite, logo e placeholder; `base.html` (pular para o conteúdo, cabeçalho, mensagens, rodapé, `{% block scripts %}`); parciais `components/` (offer_card no contrato `OfferCardVM`, selo, foto, filtros, aviso, vazio, menu de ações); `django/forms/field.html`; páginas de erro; `core/styleguide.html` e `core/privacy.html` (rascunho) | `static/css/app.css`, `static/fontes/*`, `static/{icones,logo,favicon}.svg`, `static/img/placeholder.svg`, `templates/{base.html,components/*,django/forms/field.html,errors/*,core/*}` | `/_estilos/` capturada em 375 e 1280 com Chrome headless; `scripts/verify.sh` verde | B (paralelo com 2 e 3) |
| V2 | Aplica a spec nas páginas das etapas 3 a 6 e revisa a cópia em `texts/` | `templates/{accounts,seller,public,moderation,metrics}/*`, `static/css/app.css`, `texts/*.py` (só o texto) | capturas 375/1280 com JS ligado e desligado; `scripts/verify.sh` verde | D (depois de C) |

Regras do grupo: o CSP bloqueia `style=""` inline e `<script>` inline, então nada de estilo nem script inline nos templates. Os devs do grupo C escrevem HTML semântico usando os componentes do V1 e não editam `base.html`, `components/` nem `app.css`. O que faltar vai para "Pendências" e o lead repassa ao V2.

## Testes
- **Framework:** pytest 9.2 + pytest-django 4.14 (`pyproject.toml`: `DJANGO_SETTINGS_MODULE=config.settings_test`, que fixa `SECRET_KEY` de teste, hasher MD5 e `STORAGES.default=InMemoryStorage`). As fixtures ficam em `conftest.py` na raiz (etapa 1): `make_user`, `make_seller(trusted=True, whatsapp_public=True)`, `make_offer(seller, kind=..., **campos)`, `seller_client`, `other_seller_client`, `staff_client`, `jpeg_bytes`/`png_bytes`/`fake_jpg_text` (gerados com Pillow em memória), `tz`. Relógio: as funções puras recebem `now`; as views são testadas com `time_machine.travel("2026-11-05 23:58:59-03:00")`.
- **Comandos:** suíte completa com `docker compose run --rm web pytest`; um arquivo com `docker compose run --rm web pytest apps/catalog/tests/test_availability.py -q`; um teste com `...::test_nome`; tudo de uma vez com `docker compose run --rm web scripts/verify.sh` (ruff check e format --check, `manage.py check`, `makemigrations --check --dry-run`, `check --deploy` com env de produção falsa, pytest). **Fora do Docker** (SQLite): `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`.
- **Matriz (onde cada CA é provado):** CA1 test_home + test_offer_detail + test_whatsapp_redirect (cliente sem JS por natureza); CA2 test_home (links levam os parâmetros e a âncora; "Voltar" volta com eles); CA3 test_home + test_public_a11y (um único `<a>` por `article`, placeholder quando não há foto); CA4 test_offer_detail; CA5 test_seller_page; CA6 test_signup, test_phone, test_seller_profile, test_whatsapp_redirect (sem autorização: os dígitos não aparecem no HTML de nenhuma página pública e a rota dá 404; ao revogar, sai na hora); CA7 test_seller_actions; CA8 test_signup, test_seller_offers (erro reexibe tudo; campos que não valem são ignorados); CA9 test_availability (23:58:59 sim; 23:59:00 não; 00:00 do dia seguinte não; encerramento às 14:00 → 13:59 sim, 14:00 não; confirmar depois do encerramento é recusado; virada de UTC às 21:00 locais não muda o dia); CA10 test_availability + test_seller_actions (13 d 23 h aparece; 14 d some e vira "Precisa de confirmação"; reconfirmar volta); CA11 test_seller_authz + test_seller_photos (GET e POST em editar, ação e remoção de foto de outro vendedor → 404; o banco e o storage ficam iguais); CA12 test_approvals, test_seller_offers, test_report_public, test_categories_admin; CA13 test_imaging (PNG renomeado .jpg aceito; texto renomeado .jpg recusado; mais de 5 MB recusado; 4ª foto recusada; dois arquivos WebP; sem EXIF) + test_settings (escolha de storage local/S3); CA14 test_settings (cookies), test_login, test_report_public, test_seller_photos (429) e CSRF com `Client(enforce_csrf_checks=True)` → 403; CA15 test_account_delete; CA16 test_recording (sem `Set-Cookie` nas páginas públicas e no redirecionamento; nenhuma coluna de IP ou User-Agent; prévia do WhatsApp não conta) + test_dashboard; CA17 test_ordering (estável no mesmo dia, muda no outro, compatíveis primeiro, nunca muda com cliques) + test_home; CA18 test_load_demo; CA19 verificação da etapa 1; CA20 test_public_a11y (todo campo com `<label for>`, `<img>` com `alt`, selo com texto, `lang="pt-BR"`, um `h1`).
- **Roteiro manual (fica com o qa ou o designer):** teclado em todas as telas (Tab, foco visível, pular para o conteúdo); contraste medido nas capturas; alvos de 44 px; capturas 375×812 e 1280×800 com `google-chrome --headless=new --screenshot=...` e de novo com `--blink-settings=scriptEnabled=false`; abrir o WhatsApp de verdade no celular; storage S3 com bucket real; publicação; contexto preservado ao usar o botão Voltar do navegador.

## Corte de escopo (do primeiro a sair ao último)
1. Métricas: `/admin/metricas/` e depois `recording.py`. As tabelas ficam.
2. JS opcional (`share.js`, `offer-form.js`, `enhance.js`) e troca/recuperação de senha. Sem recuperação, a página de entrar mostra "fale com a administração", como a spec prevê.
3. Administração: categorias (ficam as 5 da semente), prévia e lista de anúncios. Aprovar, ocultar e tratar denúncia são o mínimo e não saem.
4. Confirmação diária e expiração. **Não cortar**: são o CA9 e o CA10, que o dono destacou.
5. Vendedor: as ações viram só pausar e reativar.
6. Visitante: não se corta.

## Pontos para o seguranca
- Uploads (etapas 3 e 4): o Pillow decodifica o conteúdo (não confia na extensão nem no `content_type`), o limite de pixels barra bomba de descompressão, os arquivos são regravados em WebP sem EXIF/GPS, com nome UUID, e `nosniff` vai na rota `/media/`. Conferir também `DATA_UPLOAD_MAX_MEMORY_SIZE`, `FILE_UPLOAD_MAX_MEMORY_SIZE` e o tamanho total da requisição (3 × 5 MB + folga).
- Autorização: 404 para recurso de outro vendedor; `staff_required` em todo `/admin/`; o Django admin não é instalado.
- Número de WhatsApp: nunca em HTML, só no 302, e só com autorização. Revogar tira o anúncio do ar na hora.
- Limite de tentativas: guarda só o HMAC do IP por até 24 h. `TRUSTED_PROXY_HOPS` errado deixa o limite ser burlado (XFF forjado) ou faz todo mundo cair no mesmo IP do proxy. Documentar o valor por plataforma.
- CSP com `form-action` incluindo `https://wa.me` e `https://api.whatsapp.com`: o Chrome aplica `form-action` aos redirecionamentos de um envio de formulário. Sem isso, o botão quebra.
- Logs: o gunicorn não registra IP nem query string (`q` pode ter nome de pessoa); o nível do logger do banco não pode ser DEBUG em produção; a denúncia (`details`) pode conter dado pessoal de terceiro e só o admin a vê.
- `SECRET_KEY` obrigatória fora do DEBUG (a aplicação não sobe sem ela); `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` e `SECURE_PROXY_SSL_HEADER` controlados por variável de ambiente; `check --deploy` roda em `verify.sh`.
- O GET de `/whatsapp/` tem efeito colateral (contador): `rel="nofollow"`, `Disallow` no robots e filtro de robôs. É risco aceito, porque a métrica é só indício de intenção.
- A exclusão de conta é imediata no banco; os arquivos são apagados depois do commit. Com S3 e URLs assinadas, o link antigo expira sozinho.

## Riscos e como reverter
| Risco | Mitigação / reversão |
|---|---|
| Migração inicial errada | Não há dados reais: `docker compose down -v` e regerar a `0001`. Depois do primeiro deploy, toda mudança vai em migração nova; a destrutiva vai separada e aborta se houver dados |
| Busca e rodízio em Python não escalam | Servem até cerca de 2.000 anúncios ativos (a escala é de uma comunidade). Se passar disso, levar o filtro de texto para o Postgres (`unaccent` + `icontains` ou full text) sem mudar o contrato de `order_offers` |
| django-storages sem classifier para 5.2 | O S3 é opcional (padrão local). Se quebrar, fixar o storage local, que é o caminho testado |
| Volume local de mídia em PaaS efêmero | O README manda usar volume persistente (Fly volume ou Railway volume) ou S3 (Tigris, R2, B2) em produção |
| Bind mount com usuário não root no dev | UID 1000 no Dockerfile, igual ao do host |
| Sessão que atravessa a meia-noite vê a ordem mudar | Aceito: a semente é a data (CA17) |

## Decisões e suposições
- D1 Django 5.2 LTS + PostgreSQL 17 + Python 3.14 no container; SQLite só para rodar testes fora do Docker.
- D2 O fuso fica só em `COMMUNITY_TZ` (padrão `America/Sao_Paulo`), e `TIME_ZONE` = `COMMUNITY_TZ`. O banco guarda UTC.
- D3 Rotas em pt-BR (`/oferta/`, `/meus-anuncios/`, `/admin/`, conforme a spec); nomes de rota, views e código em inglês. A oferta usa o id na URL e o vendedor usa slug.
- D4 Contato: botão → `GET /oferta/<id>/whatsapp/` → 302 para `https://wa.me/55DDNUMERO?text=...`. O número nunca vai para o HTML. Sem autorização, o anúncio não é público (decisão do lead em `decisoes.md`), o que **substitui** o estado "Contato não autorizado" da spec (`spec:229`, `spec:655`).
- D5 WhatsApp aceito: celular brasileiro (DDD válido + 9 dígitos começando com 9). Fixo é recusado.
- D6 Estados públicos: `available_today`, `on_order` (recorrente sem confirmação do dia), `sold_out`, `sold`, `none` (sem selo; oferta do dia sem confirmação e venda pontual ativa). Só do vendedor: `pending_approval`, `hidden`, `paused`, `needs_confirmation`.
- D7 "Confirmar disponível hoje" vale para oferta **recorrente e do dia** (o brief diz que a recorrente "pode" estar disponível na hora). O horário de encerramento é só da oferta do dia. Na recorrente a confirmação vale até 23h59. **Diverge da `spec:254`**, que mostra o botão só na oferta do dia: o V2 ajusta.
- D8 Fotos em JPEG, PNG ou WebP, até 5 MB, 3 por anúncio, saída em WebP (480² no cartão, até 1280 px na página). Sem HEIC: o `accept` restrito faz o iOS converter para JPEG (não verificado em aparelho; está no roteiro manual).
- D9 Mídia local servida por view do Django com cache e `nosniff`. Com S3, URLs assinadas (`AWS_QUERYSTRING_AUTH=true`) e o domínio vai no `img-src` do CSP.
- D10 Venda pontual: editar, reativar ou "voltar a vender" contam como reconfirmação. "Vendido" continua na lista até 23h59 do dia da venda e a página da oferta continua acessível com o selo "Vendido".
- D11 Esgotado continua listado com o selo (na oferta do dia, o selo só vale no dia em que foi marcado; ver `docs/produto/decisoes.md`); pausado, oculto, pendente e venda pontual vencida dão 404 público, sem dizer o motivo.
- D12 A aprovação vale por vendedor: aprovar o primeiro anúncio marca `is_trusted`, e os anúncios seguintes saem aprovados. Editar um anúncio aprovado não volta para análise; o admin pode ocultar.
- D13 Busca sem acento e sem diferença de maiúsculas, em título, vendedor, descrição, variações e categoria, com todos os termos obrigatórios. Prioridade: título, depois vendedor, depois o resto; entre iguais, o rodízio. Sem busca, vale só o rodízio. "Disponíveis hoje" = `available_today`.
- D14 Alimento é definido pela **categoria** (`Category.is_food`, editável pelo admin). Na semente, "Comidas e doces" e "Bebidas" são alimento, porque bebida também tem alergênico. A spec (`spec:200`) cita só Comidas e doces: o V2 ajusta a legenda.
- D15 Métricas: as visualizações contam no GET 200 da página da oferta e os cliques no redirecionamento. Não contam HEAD, o próprio vendedor nem User-Agent de robô ou de prévia de link. O termo sem resultado é guardado normalizado, com até 60 caracteres. Nenhuma tabela de métrica tem IP, User-Agent ou cookie.
- D16 Limitador de tentativas próprio no Postgres, porque o django-ratelimit exige Redis ou memcached. Ele guarda o HMAC do IP por até 24 h. Isso não é métrica e não se aplica ao visitante que só navega; quem toca em "Consultar no WhatsApp" entra no limite de contatos (S8).
- D17 A recuperação de senha usa o fluxo do Django com `EMAIL_BACKEND` de console por padrão e SMTP por variável de ambiente (pendência documentada). O admin também pode usar `manage.py changepassword`.
- D18 O admin é um `User` com `is_staff`, criado com `docker compose exec web python manage.py createsuperuser`. Não há credencial padrão, nem na demo.
- D19 Os textos em Python ficam numa pasta (`texts/`, um módulo por área), não num arquivo único (`spec:615`), para permitir etapas paralelas.
- D20 Campos condicionais: o servidor ignora os que não valem para o tipo ou a categoria, e `offer-form.js` esconde as seções (conforme a `spec:266`). Para cumprir o "também sem JavaScript" do CA8 ao pé da letra, recomendo ao V2 esconder com CSS `:has()` dentro de `@supports selector(:has(*))`, que é o mesmo efeito sem JS e com tudo visível nos navegadores antigos. A decisão visual é do designer.
- D21 Sem "Excluir anúncio" (`spec:651`): pausar tira o anúncio da vitrine e excluir a conta remove tudo.
- D22 Admin com aba "Métricas" (`/admin/metricas/`, só tabelas). A spec não lista essa aba; sem ela, as métricas do brief não teriam onde ser lidas.
- D23 Os dados de demonstração sobem por padrão no `compose.yaml` local (`DEMO_DATA=true`) e ficam desligados no `compose.prod.yaml` e no `.env.example`. O contato de um anúncio de exemplo mostra uma página explicando que ele é fictício e nunca abre o WhatsApp.
- D24 Deploy recomendado: VPS pequena com `docker compose -f compose.yaml -f compose.prod.yaml up -d` e Caddy na frente (TLS). Alternativas: Fly.io (Dockerfile + Postgres + volume ou Tigris) e Railway (Dockerfile + plugin Postgres + volume). O README cobre as três.
- D25 Tamanho de página: 20 cartões, cumulativo (`?pagina=N` renderiza de 1 a N×20). Termo de busca truncado em 80 caracteres.

## ADR
**ADR-001: Django 5.2 LTS monolítico com PostgreSQL, renderização no servidor e sem serviços auxiliares.**
- Contexto: uma pessoa mantém, o custo deve ser mínimo, o app precisa funcionar sem JS e exige CSRF, sessão e formulários robustos.
- Decisão: Django 5.2 LTS, Postgres 17, whitenoise e gunicorn; Pillow para imagens; limitador de tentativas e métricas em tabelas do próprio banco; regras de tempo como funções puras com relógio injetado.
- Consequências: não há Redis nem fila, então tudo o que depende de tempo é calculado na leitura (o brief exige isso). Busca e rodízio rodam em Python e servem até cerca de 2.000 anúncios. A troca para LTS 6.2 fica para 2027/2028.

## Texto para o lead preencher "Contexto do projeto" no CLAUDE.md
```
- **Produto:** "Pão de Cada Dia", vitrine gratuita de compra e venda entre estudantes do Campus Paraíso (UFLA/ICTIN, MG). Visitante sem cadastro encontra a oferta e chama o vendedor no WhatsApp; vendedor mantém anúncios com um clique; admin aprova o 1º anúncio e trata denúncias. Brief: `docs/produto/briefs/vitrine-mvp.md`.
- **Stack:** Python 3.14, Django 5.2 LTS, PostgreSQL 17 (SQLite só para testes fora do Docker), templates do Django renderizados no servidor, CSS único, JS opcional e mínimo; Pillow (imagens), whitenoise, gunicorn, django-storages + boto3 (S3 opcional). Docker Compose para rodar local.
- **Camadas e pastas:** `apps/<app>/` (core, accounts, catalog, moderation, metrics). Regras de tempo, estado, busca, rodízio, preço e WhatsApp são funções puras em `apps/catalog/domain/`; views finas em `views_*.py`; serviços em `services*.py`/`photos.py`; telefone em `apps/accounts/phone.py`. **Regra de negócio — o designer não toca:** `apps/`, `config/`, `docker/`, `scripts/`, `static/js/`, `conftest.py`, `requirements*.txt`, `pyproject.toml`, `compose*.yaml`, `Dockerfile`. **Apresentação:** `templates/` (base, `components/`, páginas por área), `static/css/app.css`, `static/fontes/` (woff2 self-hosted + OFL), `static/icones.svg`, `static/logo.svg`. **Textos de interface:** os que nascem no Python ficam em `texts/<área>.py` (constantes); texto fixo de página fica no template.
- **Verificação:** tudo: `docker compose run --rm web scripts/verify.sh` (ruff, check, makemigrations --check, check --deploy, pytest). Suíte: `docker compose run --rm web pytest`. Um arquivo: `docker compose run --rm web pytest apps/catalog/tests/test_availability.py -q`. Fora do Docker: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`. Subir: `docker compose up` → http://localhost:8000.
- **Dados de teste:** `DEMO_DATA=true` (padrão do compose local) carrega dados marcados "(exemplo)" via `python manage.py load_demo`; sem a variável o comando recusa. Testes não usam serviço externo: storage em memória, e-mail no console, relógio com time-machine. Admin local: `docker compose exec web python manage.py createsuperuser`.
- **Dado pessoal (LGPD):** `accounts_user.email`, `catalog_seller` (nome, apresentação, região, horários, `whatsapp_number`), `moderation_report.details` (texto livre), sessões. `core_ratelimitcounter` guarda só HMAC de IP/e-mail por até 24 h. Métricas (`metrics_*`) são agregadas por dia, sem IP, User-Agent nem cookie. O número de WhatsApp nunca vai para HTML (só no 302 de `/oferta/<id>/whatsapp/`, com autorização). Nunca em logs nem em mensagens de erro; o gunicorn não registra IP nem query string.
- **Segredos:** nunca leia nem imprima `.env*` (exceto `.env.example`) nem arquivos de senha.
- **Docs que acompanham a mudança:** `README.md` (rodar local e publicar), `.env.example` (toda variável nova, explicada), `docs/produto/decisoes.md` (decisões do dono).
```
