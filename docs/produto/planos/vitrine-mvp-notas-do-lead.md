# Notas do lead — vitrine-mvp, grupo C

Complementa `docs/produto/planos/vitrine-mvp.md`. Linha de base ao abrir o grupo C (2026-11-05): `docker compose run --rm web scripts/verify.sh` verde, **418 testes passando**.

## O que já existe (grupos A e B)
- Etapa 1: fundação, modelos, rotas congeladas com stubs 501, `conftest.py`, `apps/core/testing.py` (helpers `assert_accessible_page`, `assert_no_inline_code`, `assert_phone_absent`, `assert_no_set_cookie`, `assert_single_link_per_article`, `make_image_bytes`…).
- Etapa 2: `apps/catalog/domain/*` (availability, states, actions com `ActionNotAllowed`, ordering, search, pricing, whatsapp), filtros `brl` e `state_vm` em `catalog_ui`, `texts/states.py`, `texts/whatsapp.py`, `load_demo`.
- Etapa 3: contas (`apps/accounts/`), `apps/catalog/imaging.py` real, `texts/accounts.py`, `texts/photos.py` (**erros de foto: a etapa 4 importa daqui**), `static/js/enhance.js` (foco, mostrar senha, "Salvando…"), limite de corpo 413.
- V1 (designer): `static/css/app.css`, fontes, `static/icones.svg`, `templates/base.html`, `templates/components/*`, `templates/django/forms/field.html`, páginas de erro, `/_estilos/` (styleguide, só com DEBUG: **abra `templates/core/styleguide.html` para ver cada classe em uso**).

## Contratos de template (V1) — use, não edite
Os `dev` do grupo C **não editam** `templates/base.html`, `templates/components/`, `templates/django/forms/field.html` nem `static/css/app.css`. Falta de classe ou componente vai para "Pendências" e o lead repassa ao designer (V2). Nada de `style=""`, `<style>` ou `<script>` inline (CSP).

- **Blocos do `base.html`:** `title`, `content`, `scripts`, `head`, `faixa` (só a página inicial, dentro de `header.cabecalho`), `body_attrs`, `main_classes`. As mensagens do Django já aparecem antes do `content`, dentro de `main > .container`.
- **Faixa da página inicial:** `{% block faixa %}<div class="container cabecalho__faixa"><p class="cabecalho__assinatura">…</p><h1>…</h1>{% include "components/busca.html" with tema="escuro" … %}</div>{% endblock %}`
- **Parciais** (`{% include "components/X.html" with … %}`):
  - `offer_card.html`: `card` = `OfferCardVM` do plano. Vai em `<ul class="lista-ofertas"><li>…</li></ul>` sob um `<h2>`; o título do cartão é `h3`.
  - `selo.html`: `state` (StateVM com `key`, `label`, `icon`). Keys: `available_today`, `on_order`, `sold_out`, `sold`, `paused`, `needs_confirmation`, `pending_approval`, `hidden`.
  - `foto.html`: `url` (vazio vira placeholder), `w`, `h`, `alt`, `eager`, `prioridade`, `legenda`, `classe`. Na página da oferta, `classe="foto--pagina"`.
  - `icone.html`: `nome` (ids do sprite, listados no styleguide), `classe` opcional (`icone--grande`, `icone--xg`).
  - `busca.html`: `q`, `cat`, `hoje`, `action`, `tema`.
  - `filtros.html`: `categories` (itens com `label`, `url`, `active`; o primeiro é "Tudo"), `today_url`, `today_active`.
  - `aviso.html`: `tipo` (`success|info|warning|error`) e `texto`.
  - `aviso_contato.html`: sem parâmetros. É o aviso "abrir o WhatsApp não é pedido confirmado".
  - `vazio.html`: `titulo`, `texto`, `acao_url`, `acao_texto`, `icone`.
  - `menu_acoes.html`: `action_url` e `actions` (itens com `key` e `label`). Cada ação vira `<button name="action" value="<key>">` num form POST com CSRF. **Decisão do lead: o campo POST da rota `/meus-anuncios/<pk>/acao/` se chama `action`** (o plano dizia `acao`), com os valores de `domain.actions.ACTIONS`.
- **Formulários:**
  - Envoltório: `<form class="form">`. Os campos saem com `{{ form.as_div }}` ou `{{ field.as_field_group }}`, que usam o `field.html`: classe `.campo`, "(opcional)" automático e erro com id `<id>_error`.
  - Resumo de erros: `<div class="aviso aviso--error" role="alert">`, com uma lista de links para `#{{ field.id_for_label }}`. Já existe `templates/accounts/_form_errors.html`, que dá para reaproveitar com `include`.
  - Botões: `.botao` com `--primario`, `--secundario`, `--confirmar`, `--perigo` ou `--link`; `--bloco-mobile` ocupa a largura toda no celular. Linha de botões: `.acoes-form`. Larguras: `.pagina-estreita` e `.pagina-form`.
- **Formulário de anúncio (D20):**
  - `<form class="form form-oferta" enctype="multipart/form-data">`.
  - Campo `kind` com os valores `recurring`, `daily` e `one_off`. Campo `category`, em que cada `<option>` de categoria de alimento leva o atributo `data-food` (use um widget `Select` com `create_option`).
  - Seções condicionais: `<fieldset class="secao-condicional so-dia">` e `<fieldset class="secao-condicional so-comida">`, cada uma com `<legend>` e a instrução "Preencha só se…". O CSS esconde as que não valem com `:has()`.
  - O servidor sempre ignora os campos que não valem para o tipo ou para a categoria.
  - Opções em forma de cartão: `label.opcao`, com o preço em `.opcao__preco`.
- **Classes de página:**
  - Página da oferta: `.oferta-pagina`, com `__fotos`, `__miniaturas`, `__conteudo` e `__retirada`.
  - Navegação e vendedor: `.voltar`, `.vendedor-bloco` (com `__iniciais`) e `dl.alimento`.
  - Link para copiar: `.copiar-link`, um input readonly.
  - Painel do vendedor: `.anuncio` e `.lista-anuncios`.
  - Administração: `.admin-nav`, `.tabela` e `.tabela-rolavel`.
  - Texto: `.texto-corrido` e `.lista-titulo`.
  - Não se preocupe com acabamento visual: o V2 refina.

## Regras de paralelismo do grupo C
- Rodam juntos: etapa 4 (vendedor), etapa 5 (admin e leitura de métricas) e etapa 6 (vitrine pública, contato, denúncia e gravação de métricas). Cada um só edita os arquivos da própria linha no plano, mais o que esta nota atribui.
- Congelados (pare e descreva em Pendências): `models.py`, `urls*.py`, `settings*.py`, `conftest.py`, `apps/core/*`, `apps/catalog/domain/*`, `apps/catalog/imaging.py`, `texts/` de outras áreas, `templates/base.html`, `templates/components/`, `static/css/`.
- **Testes:** rode com SQLite, para não colidir no banco de teste do Postgres: `docker compose run --rm -e POSTGRES_HOST= web pytest <arquivos> -q`. Ruff: `docker compose run --rm -e POSTGRES_HOST= web ruff check <arquivos>` e `ruff format <só os seus arquivos>` (**nunca numa pasta inteira**). Não suba `docker compose up` na porta 8000 e não apague volumes. Se precisar ver no navegador, use `-p 801X:8000` com X = número da etapa. Apague o `db.sqlite3` que sobrar na raiz.
- Não rode o `verify.sh` completo: a verificação integrada é do lead.

## Atribuições extras do lead
- **Etapa 4:**
  - `data-food` nas opções de categoria.
  - Perfil do vendedor com os links "Trocar senha" (`accounts:password_change`) e "Excluir minha conta" (`accounts:delete`).
  - Aviso no painel quando o WhatsApp não está liberado (D4: anúncios não aparecem ao público) e quando há anúncio aguardando aprovação.
  - Os erros de foto vêm de `texts/photos.py`.
- **Etapa 5:**
  - Tudo sob `staff_required`. Prévia do anúncio pendente para o admin, mesmo não sendo público.
  - Aprovar marca `seller.is_trusted` e aprova o anúncio.
  - Ocultar e mostrar, com motivo; tratar denúncia (resolver, e ocultar se for o caso).
  - Categorias: criar, renomear, posição, `is_active`, `is_food`. Não dá para excluir.
  - Métricas em tabela dos últimos 30 dias.
- **Etapa 6:**
  - Página 404 de oferta indisponível com contexto: renderizar `errors/404.html` com `title="Esta oferta não está mais disponível"`, `message` e `action_label="Ver outras ofertas"`, e `status=404`.
  - `load_demo` já roda na subida local: a página inicial deve mostrar esses dados.
  - Anúncios de exemplo abrem `public/demo_contact.html`, nunca o WhatsApp.
