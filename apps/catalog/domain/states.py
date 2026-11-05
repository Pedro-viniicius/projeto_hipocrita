"""Estados de um anúncio, para o público e para o vendedor (D6)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from texts import states as texts

from .availability import (
    ACTIVE,
    ONE_OFF,
    PAUSED,
    SOLD,
    is_available_today,
    needs_reconfirmation,
)

SOLD_OUT = "sold_out"


class PublicState(StrEnum):
    AVAILABLE_TODAY = "available_today"
    ON_ORDER = "on_order"
    SOLD_OUT = "sold_out"
    SOLD = "sold"
    NONE = "none"  # sem selo (spec:166)


class SellerState(StrEnum):
    """Estados que o vendedor vê: os públicos mais os que só ele conhece."""

    PENDING_APPROVAL = "pending_approval"
    HIDDEN = "hidden"
    PAUSED = "paused"
    NEEDS_CONFIRMATION = "needs_confirmation"
    AVAILABLE_TODAY = "available_today"
    ON_ORDER = "on_order"
    SOLD_OUT = "sold_out"
    SOLD = "sold"
    NONE = "none"


@dataclass(frozen=True)
class StateVM:
    key: str
    label: str
    icon: str


def _changed_today(offer, now: datetime, tz: ZoneInfo) -> bool:
    """O estado mudou hoje, no fuso da comunidade."""
    return offer.status_changed_at.astimezone(tz).date() == now.astimezone(tz).date()


def public_state(offer, now: datetime, tz: ZoneInfo) -> PublicState:
    """Selo público. Venda pontual ativa e oferta do dia sem confirmação ficam sem selo.

    Oferta do dia esgotada mostra "Esgotado" só no dia em que foi marcada; nos dias
    seguintes fica sem selo, como a do dia sem confirmação (decisão do lead, aguardando
    validação do dono; ver `docs/produto/decisoes.md`).
    """
    if offer.status == SOLD:
        return PublicState.SOLD
    if offer.status == SOLD_OUT:
        if offer.kind == "daily" and not _changed_today(offer, now, tz):
            return PublicState.NONE
        return PublicState.SOLD_OUT
    if offer.status == PAUSED or offer.kind == ONE_OFF:
        return PublicState.NONE
    closing = offer.closing_time if offer.kind == "daily" else None
    if is_available_today(offer.daily_confirmed_on, closing, now, tz):
        return PublicState.AVAILABLE_TODAY
    if offer.kind == "recurring":
        return PublicState.ON_ORDER
    return PublicState.NONE


def seller_state(offer, now: datetime, tz: ZoneInfo, days: int) -> SellerState:
    """Oculto > aguardando aprovação > pausado > precisa de confirmação > estado público."""
    if offer.hidden_at is not None:
        return SellerState.HIDDEN
    if offer.approval != "approved":
        return SellerState.PENDING_APPROVAL
    if offer.status == PAUSED:
        return SellerState.PAUSED
    if (
        offer.kind == ONE_OFF
        and offer.status == ACTIVE
        and needs_reconfirmation(offer.last_confirmed_at, now, days)
    ):
        return SellerState.NEEDS_CONFIRMATION
    if offer.status == SOLD_OUT:
        # O vendedor sempre vê "Esgotado", mesmo quando o público já não vê o selo.
        return SellerState.SOLD_OUT
    return SellerState(public_state(offer, now, tz).value)


def state_vm(state: str) -> StateVM | None:
    """Rótulo e ícone do selo. `none` (sem selo) devolve `None`."""
    key = str(state)
    if key not in texts.STATES:
        return None
    label, icon = texts.STATES[key]
    return StateVM(key=key, label=label, icon=icon)
