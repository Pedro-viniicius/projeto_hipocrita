"""Regras de tempo e visibilidade (CA9, CA10). Funções puras: sem ORM, o relógio é injetado.

"Hoje" e "agora" sempre no fuso da comunidade (`tz`); `now` pode vir em qualquer
fuso (normalmente UTC) e é convertido aqui.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

END_OF_DAY = time(23, 59)

# Valores de `Offer.status`/`approval`/`kind` (o domínio não importa o modelo).
ACTIVE = "active"
PAUSED = "paused"
SOLD = "sold"
APPROVED = "approved"
ONE_OFF = "one_off"


def _local(now: datetime, tz: ZoneInfo) -> datetime:
    return now.astimezone(tz)


def daily_expires_at(confirmed_on: date, closing_time: time | None, tz: ZoneInfo) -> datetime:
    """Fim da confirmação: o horário de encerramento ou 23:59, o que vier primeiro (CA9)."""
    limit = min(closing_time or END_OF_DAY, END_OF_DAY)
    return datetime.combine(confirmed_on, limit.replace(tzinfo=None), tzinfo=tz)


def is_available_today(
    confirmed_on: date | None, closing_time: time | None, now: datetime, tz: ZoneInfo
) -> bool:
    """A confirmação vale só no dia dela e até o fim calculado acima (CA9)."""
    if confirmed_on is None:
        return False
    local = _local(now, tz)
    return confirmed_on == local.date() and local < daily_expires_at(confirmed_on, closing_time, tz)


def needs_reconfirmation(last_confirmed_at: datetime, now: datetime, days: int) -> bool:
    """Venda pontual sem reconfirmação há `days` dias ou mais (CA10)."""
    return now - last_confirmed_at >= timedelta(days=days)


def has_public_contact(seller, *, demo_enabled: bool = False) -> bool:
    """Contato público: WhatsApp autorizado e cadastrado, ou vendedor de demonstração
    quando os dados de exemplo estão ligados (`demo_enabled`, de `settings.DEMO_DATA`).

    O padrão `False` é o seguro: quem esquecer de passar não publica a demonstração.
    """
    if seller.is_demo and demo_enabled:
        return True
    return bool(seller.whatsapp_public and seller.whatsapp_number)


def _one_off_expired(offer, now: datetime, days: int) -> bool:
    return (
        offer.kind == ONE_OFF
        and offer.status == ACTIVE
        and needs_reconfirmation(offer.last_confirmed_at, now, days)
    )


def is_page_visible(
    offer, now: datetime, tz: ZoneInfo, days: int, *, demo_enabled: bool = False
) -> bool:
    """A página da oferta abre para o público (senão, 404 sem dizer o motivo)."""
    return (
        offer.approval == APPROVED
        and offer.hidden_at is None
        and offer.seller.user.is_active
        and has_public_contact(offer.seller, demo_enabled=demo_enabled)
        and offer.status != PAUSED
        and not _one_off_expired(offer, now, days)
    )


def _sold_today(offer, now: datetime, tz: ZoneInfo) -> bool:
    """ "Vendido" fica na lista até 23:59 do dia da venda, no fuso da comunidade (D10)."""
    return is_available_today(_local(offer.status_changed_at, tz).date(), None, now, tz)


def is_listed(offer, now: datetime, tz: ZoneInfo, days: int, *, demo_enabled: bool = False) -> bool:
    """Aparece na lista pública."""
    if not is_page_visible(offer, now, tz, days, demo_enabled=demo_enabled):
        return False
    return offer.status != SOLD or _sold_today(offer, now, tz)


def can_contact(
    offer, now: datetime, tz: ZoneInfo, days: int, *, demo_enabled: bool = False
) -> bool:
    """O botão do WhatsApp funciona: página visível e anúncio ativo."""
    return (
        is_page_visible(offer, now, tz, days, demo_enabled=demo_enabled) and offer.status == ACTIVE
    )
