#!/bin/sh
# Build na Vercel ([tool.vercel.scripts] do pyproject.toml). Roda depois de
# instalar as dependências; o collectstatic a Vercel roda sozinha.
#
# - Produção: aplica as migrações pela conexão direta do Neon (PGHOST_UNPOOLED),
#   não pelo pooler, que não segura a sessão inteira de um `migrate`.
#   Os previews nem chegam aqui (ignoreCommand do vercel.json).
# - Sempre: `check --deploy` no log do build. Aviso não derruba o build; erro, sim.
set -eu
cd "$(dirname "$0")/.."

if [ "${VERCEL_ENV:-}" = "production" ]; then
  # Sem host, o Django cairia no SQLite do próprio build e o banco real ficaria
  # sem as migrações: melhor falhar aqui.
  migrate_host="${PGHOST_UNPOOLED:-${POSTGRES_HOST:-}}"
  if [ -z "$migrate_host" ]; then
    echo "Erro: defina POSTGRES_HOST (e PGHOST_UNPOOLED, do Neon) no ambiente Production." >&2
    exit 1
  fi
  echo "== migrate (conexão direta)"
  POSTGRES_HOST="$migrate_host" python manage.py migrate --noinput
fi

echo "== check --deploy"
python manage.py check --deploy
