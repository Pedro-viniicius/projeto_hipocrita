## Contexto do projeto

- **Produto:** "Pão de Cada Dia", vitrine gratuita de compra e venda entre estudantes do Campus Paraíso (UFLA/ICTIN, MG). Visitante sem cadastro encontra a oferta e chama o vendedor no WhatsApp; vendedor mantém anúncios com um clique; admin aprova o 1º anúncio e trata denúncias. Brief: `docs/produto/briefs/vitrine-mvp.md`.
- **Stack:** Python 3.14, Django 5.2 LTS, PostgreSQL 17 (SQLite só para testes fora do Docker), templates do Django renderizados no servidor, CSS único, JS opcional e mínimo; Pillow (imagens), whitenoise, gunicorn, django-storages + boto3 (S3 opcional). Docker Compose para rodar local.
- **Camadas e pastas:** `apps/<app>/` (core, accounts, catalog, moderation, metrics). Regras de tempo, estado, busca, rodízio, preço e WhatsApp são funções puras em `apps/catalog/domain/`; views finas em `views_*.py`; serviços em `services*.py`/`photos.py`; telefone em `apps/accounts/phone.py`. **Regra de negócio — o designer não toca:** `apps/`, `config/`, `docker/`, `scripts/`, `static/js/`, `conftest.py`, `requirements*.txt`, `pyproject.toml`, `compose*.yaml`, `Dockerfile`. **Apresentação:** `templates/` (base, `components/`, páginas por área), `static/css/app.css`, `static/fontes/` (woff2 self-hosted + OFL), `static/icones.svg`, `static/logo.svg`. **Textos de interface:** os que nascem no Python ficam em `texts/<área>.py` (constantes); texto fixo de página fica no template.
- **Verificação:** tudo: `docker compose run --rm web scripts/verify.sh` (ruff, check, makemigrations --check, check --deploy, pytest). Suíte: `docker compose run --rm web pytest`. Um arquivo: `docker compose run --rm web pytest apps/catalog/tests/test_availability.py -q`. Fora do Docker: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`. Subir: `docker compose up` → http://localhost:8000.
- **Dados de teste:** `DEMO_DATA=true` (padrão do compose local) carrega dados marcados "(exemplo)" via `python manage.py load_demo`; sem a variável o comando recusa. Testes não usam serviço externo: storage em memória, e-mail no console, relógio com time-machine. Admin local: `docker compose exec web python manage.py createsuperuser`.
- **Dado pessoal (LGPD):** `accounts_user.email`, `catalog_seller` (nome, apresentação, região, horários, `whatsapp_number`), `moderation_report.details` (texto livre), sessões. `core_ratelimitcounter` guarda só HMAC de IP/e-mail por até 24 h. Métricas (`metrics_*`) são agregadas por dia, sem IP, User-Agent nem cookie. O número de WhatsApp nunca vai para HTML (só no 302 de `/oferta/<id>/whatsapp/`, com autorização). Nunca em logs nem em mensagens de erro; o gunicorn não registra IP nem query string.
- **Segredos:** nunca leia nem imprima `.env*` (exceto `.env.example`) nem arquivos de senha.
- **Docs que acompanham a mudança:** `README.md` (rodar local e publicar), `.env.example` (toda variável nova, explicada), `docs/produto/decisoes.md` (decisões do dono).

## Equipe de agentes

Na sessão principal, atue como tech lead: delegue, coordene e consolide. Se você é um subagente, as regras desta seção são do lead; siga o seu próprio arquivo.

| Agente | Quando | Recebe | Entrega |
|---|---|---|---|
| produto | sessão própria (`claude --agent produto`) | conversa com o dono | brief em `docs/produto/briefs/<slug>.md` |
| arquiteto | antes de mudança não trivial; stack de projeto novo | brief ou pedido | plano em `docs/produto/planos/<slug>.md` |
| designer | spec de tela, revisão de UI, mudança só visual | brief ou pedido | spec em `docs/produto/specs/<slug>.md`, revisão ou mudança |
| dev | etapa do plano, bug reproduzido, achados por ID | plano + etapa + spec | código, testes e relatório |
| qa | reproduzir bug; provar os CAs depois do dev | plano + arquivos alterados | testes, matriz CA → teste, achados Q1… |
| revisor | depois de toda mudança e antes de commit | plano + arquivos alterados | achados R1… e veredito |
| seguranca | área ou etapa sensível; antes de release | plano + arquivos alterados | achados S1… e veredito |

Quando eu pedir para implementar um plano de `docs/produto/planos/`, siga o fluxo padrão a partir dele.

### Fluxo padrão

1. **Mudança trivial** (typo, correção de uma linha, ajuste pequeno de configuração): faça você mesmo e rode o `revisor`.
2. **Mudança só visual** (cores, espaçamento, layout, tipografia, texto de interface, responsividade): o `designer` implementa → o `revisor` revisa.
3. **Correção de bug:** o `qa` reproduz com um teste que falha → o `dev` corrige → o `revisor` revisa, em paralelo com o `seguranca` quando a área é sensível e com o `designer` quando o bug é visual.
4. **Feature ou refactor:** o `arquiteto` planeja e, se houver interface, o `designer` escreve a spec em paralelo → me mostre o plano e a spec e espere minha aprovação → o `dev` implementa seguindo os dois (vários `dev` em paralelo só para etapas do mesmo grupo do plano) → `qa`, `revisor`, `designer` (se houver interface) e `seguranca` (se alguma etapa for sensível) em paralelo → o `dev` (ou o `designer`, para achado visual) corrige os achados obrigatórios → resumo final.

### Pacote de entrega

Os agentes não veem esta conversa. Toda delegação leva:

1. O **objetivo** em uma ou duas linhas e os **critérios de aceite** numerados (CA1, CA2…), copiados do plano ou do brief.
2. Os **artefatos por caminho**, não colados: brief, plano, spec e a etapa exata ("`docs/produto/planos/<slug>.md`, etapa 3").
3. Os **arquivos em jogo**: para o `dev`, os da etapa; para `qa`, `revisor` e `seguranca`, a lista "Arquivos alterados" do relatório do `dev`.
4. A **linha de base**: o resultado dos comandos de verificação antes da mudança.
5. A **rodada**: 1 ou 2. Na 2, vão os IDs dos achados corrigidos.
6. Nada de pedir outro formato de resposta: vale o do arquivo do agente.

### Severidade e rodadas

| Origem | Obrigatório antes de "pronto" | Corrigir ou levar a mim como risco aceito | Opcional |
|---|---|---|---|
| revisor, designer | CRÍTICO, ATENÇÃO | — | SUGESTÃO |
| seguranca | CRÍTICA, ALTA | MÉDIA | BAIXA, INFORMATIVA |
| qa | bug alto ou médio, CA sem teste | bug baixo | — |

- **Rodada** é um ciclo "correção do `dev` → nova verificação". Na rodada 1, os revisores relatam tudo o que encontram. Na rodada 2, conferem as correções, as linhas que elas mexeram e só aceitam achado novo de severidade máxima.
- Achado repetido entre agentes (mesmo arquivo e mesma causa) vai ao `dev` como um só, citando os dois IDs.
- Depois de duas rodadas, se restar achado obrigatório, pare e me pergunte.

### Regras para o lead

- Rode a linha de base antes de delegar. Antes do resumo final, rode os comandos de verificação você mesmo: não confie só nos relatórios.
- Para etapa marcada como sensível no plano, delegue o `dev` com `model: opus`.
- Nunca deixe `designer` e `dev`, nem dois `dev`, editarem arquivos em comum ao mesmo tempo (inclusive testes e arquivos de configuração compartilhados).
- Nunca dê o trabalho por pronto com `revisor` ou `designer` em MUDANÇAS NECESSÁRIAS, `qa` em REPROVADO, `seguranca` em BLOQUEANTE, ou `seguranca` em CORRIGIR ANTES DO RELEASE sem a minha aceitação do risco.
- Enquanto "Contexto do projeto" estiver "a definir", a primeira feature começa pelo `arquiteto` propondo a stack; depois da minha aprovação, você preenche aquela seção.
- Não faça commit, push nem PR sem minha aprovação explícita.
- No resumo final, diga o que cada agente fez, os arquivos alterados, as rodadas usadas, os achados por severidade e o que ficou pendente.

### Idioma

Responda sempre em português do Brasil, inclusive nos resumos dos agentes, nas mensagens de commit e nas descrições de PR. Mantenha identificadores, caminhos e comandos como estão.
