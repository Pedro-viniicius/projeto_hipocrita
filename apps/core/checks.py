"""System checks do projeto (rodam com `python manage.py check --deploy`)."""

import re

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def privacy_controller_check(app_configs, **kwargs) -> list[Warning]:
    """Avisa quando a página de privacidade ainda mostra "Responsável: a definir"."""
    missing = [
        name
        for name in ("PRIVACY_CONTROLLER_NAME", "PRIVACY_CONTACT_EMAIL")
        if not getattr(settings, name, "")
    ]
    if not missing:
        return []
    return [
        Warning(
            f"Faltam {' e '.join(missing)}: a página /privacidade/ mostra "
            '"a definir" no lugar do responsável pelos dados e do contato (LGPD art. 9).',
            hint="Preencha as variáveis no .env (ver .env.example).",
            id="core.W001",
        )
    ]


# Caracteres seguros num cabeçalho HTTP e em qualquer painel (token68 da RFC 7235).
CRON_SECRET_CHARS = re.compile(r"[A-Za-z0-9._~+/=-]+")
CRON_SECRET_MIN_LENGTH = 32


@register(Tags.security, deploy=True)
def cron_secret_check(app_configs, **kwargs) -> list[Warning]:
    """Avisa quando o `CRON_SECRET` é curto ou tem caractere fora do recomendado.

    Não mostra o valor: só o tamanho mínimo e o conjunto de caracteres aceitos.
    """
    secret = getattr(settings, "CRON_SECRET", "")
    if not secret:
        return []
    if len(secret) >= CRON_SECRET_MIN_LENGTH and CRON_SECRET_CHARS.fullmatch(secret):
        return []
    return [
        Warning(
            f"CRON_SECRET deve ter pelo menos {CRON_SECRET_MIN_LENGTH} caracteres, só letras "
            'sem acento, números e ". _ ~ + / = -": ele vai num cabeçalho HTTP e protege a '
            "rota /_tarefas/limpeza/.",
            hint='Gere outro com: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
            " e troque na Vercel e no GitHub (README).",
            id="core.W002",
        )
    ]
