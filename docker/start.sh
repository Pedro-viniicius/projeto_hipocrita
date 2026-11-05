#!/bin/sh
# Produção: aplica migrações, apaga dados vencidos e sobe o gunicorn.
set -eu
python manage.py migrate --noinput
# Sessões vencidas e dados fora do prazo de guarda (ver apps/core/retention.py).
# Falha na limpeza não impede o app de subir.
python manage.py cleanup_data || echo "Aviso: cleanup_data falhou; o app sobe mesmo assim." >&2
exec gunicorn config.wsgi:application --config docker/gunicorn.conf.py
