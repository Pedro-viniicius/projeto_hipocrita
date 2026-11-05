"""Tira dos logs o link de redefinição de senha.

O caminho `/senha/redefinir/<uid>/<token>/` (rota em `apps/accounts/urls.py`)
leva o token que troca a senha de alguém. Quem lê o log não pode usá-lo, então
tudo depois de `/senha/redefinir/` vira `***`, no log do Django e no do gunicorn.

Sem import do Django: o gunicorn carrega este módulo antes do app.
"""

import logging
import re

from gunicorn import glogging

RESET_PREFIX = "/senha/redefinir/"
MASK = "***"
_RESET_RE = re.compile(re.escape(RESET_PREFIX) + r"[^\s\"']*")


def redact_reset_links(text: str) -> str:
    """Troca uid, token e query string de `/senha/redefinir/...` por `***`."""
    return _RESET_RE.sub(RESET_PREFIX + MASK, text)


class RedactPasswordResetLinks(logging.Filter):
    """Filtro de log: aplica `redact_reset_links` à mensagem já formatada."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # mensagem mal formada: deixa o logging tratar
            return True
        if RESET_PREFIX in message:
            record.msg = redact_reset_links(message)
            record.args = None
        return True


class GunicornLogger(glogging.Logger):
    """Logger do gunicorn (`logger_class`) com o filtro no access log e no error log."""

    def setup(self, cfg) -> None:
        super().setup(cfg)
        for log in (self.error_log, self.access_log):
            if not any(isinstance(f, RedactPasswordResetLinks) for f in log.filters):
                log.addFilter(RedactPasswordResetLinks())
