#!/bin/sh
# Espera o PostgreSQL aceitar conexão (até 60 s) e executa o comando pedido.
set -eu

if [ -n "${POSTGRES_HOST:-}" ]; then
  python - <<'PY'
import os
import socket
import sys
import time

host = os.environ["POSTGRES_HOST"]
port = int(os.environ.get("POSTGRES_PORT") or 5432)
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        time.sleep(1)
print("Banco de dados indisponível após 60 s.", file=sys.stderr)
sys.exit(1)
PY
fi

exec "$@"
