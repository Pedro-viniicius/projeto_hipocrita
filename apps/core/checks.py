"""System checks do projeto (rodam com `python manage.py check --deploy`)."""

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
