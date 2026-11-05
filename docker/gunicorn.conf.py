"""Configuração do gunicorn em produção.

O log de acesso não registra IP nem query string (a busca `q` pode ter nome de
pessoa): só data, método, caminho, status, tamanho e duração. O caminho
`/senha/redefinir/<uid>/<token>/` sai como `/senha/redefinir/***`
(`apps.core.redaction.GunicornLogger`), no log de acesso e no de erros.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
# %(U)s = caminho sem query string; sem %(h)s (IP), %(q)s, %(r)s, %(f)s nem %(a)s.
access_log_format = '%(t)s "%(m)s %(U)s" %(s)s %(B)s %(M)sms'
logger_class = "apps.core.redaction.GunicornLogger"

# Aceita X-Forwarded-Proto só de proxies na rede interna (Caddy, Fly, Railway).
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
