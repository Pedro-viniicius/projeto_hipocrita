#!/bin/sh
# Desenvolvimento: migrações, dados de exemplo (com DEMO_DATA=true) e runserver.
set -eu
python manage.py migrate --noinput

case "$(echo "${DEMO_DATA:-false}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|sim|on)
    # Falha na carga de exemplo não impede o app de subir.
    python manage.py load_demo || echo "Aviso: load_demo falhou; o app sobe sem dados de exemplo." >&2
    ;;
esac

exec python manage.py runserver 0.0.0.0:"${PORT:-8000}"
