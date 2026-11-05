#!/bin/sh
# Verificação completa: lint, formatação, checks do Django, migrações pendentes,
# checagem de deploy com ambiente de produção falso e testes.
set -eu
cd "$(dirname "$0")/.."

echo "== ruff check"
ruff check .
echo "== ruff format --check"
ruff format --check .

echo "== manage.py check"
DJANGO_SETTINGS_MODULE=config.settings_test python manage.py check

echo "== makemigrations --check"
DJANGO_SETTINGS_MODULE=config.settings_test python manage.py makemigrations --check --dry-run

echo "== check --deploy (ambiente de produção falso)"
env -u COOKIE_SECURE -u STORAGE_BACKEND DJANGO_SETTINGS_MODULE=config.settings \
  DEBUG=false \
  SECRET_KEY="verify-$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  ALLOWED_HOSTS=exemplo.invalid \
  CSRF_TRUSTED_ORIGINS=https://exemplo.invalid \
  SECURE_PROXY_SSL_HEADER=true \
  SECURE_SSL_REDIRECT=true \
  SECURE_HSTS_SECONDS=31536000 \
  PRIVACY_CONTROLLER_NAME="Responsável fictício" \
  PRIVACY_CONTACT_EMAIL=privacidade@exemplo.invalid \
  POSTGRES_HOST= \
  python manage.py check --deploy --fail-level WARNING

echo "== pytest"
pytest -q "$@"
