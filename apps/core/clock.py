"""Relógio único do app. Views e serviços pegam "agora" e o fuso só daqui.

Nos testes de view, o relógio é controlado com `time_machine.travel(...)`.
"""

from datetime import datetime
from functools import cache
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def now() -> datetime:
    """Agora, com fuso (UTC)."""
    return timezone.now()


@cache
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def community_tz() -> ZoneInfo:
    """Fuso da comunidade (`settings.COMMUNITY_TZ`)."""
    return _zone(settings.COMMUNITY_TZ)
