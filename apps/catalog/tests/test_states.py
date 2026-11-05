"""Estados públicos e do vendedor (D6) e seus rótulos."""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.catalog.domain.states import (
    PublicState,
    SellerState,
    public_state,
    seller_state,
    state_vm,
)

TZ = ZoneInfo("America/Sao_Paulo")
DAY = date(2026, 11, 5)
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=TZ)


def offer(**kw):
    base = dict(
        kind="recurring",
        status="active",
        approval="approved",
        hidden_at=None,
        daily_confirmed_on=None,
        closing_time=None,
        last_confirmed_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_public_states():
    assert public_state(offer(status="sold", kind="one_off"), NOW, TZ) == PublicState.SOLD
    assert public_state(offer(status="sold_out"), NOW, TZ) == PublicState.SOLD_OUT
    assert public_state(offer(daily_confirmed_on=DAY), NOW, TZ) == PublicState.AVAILABLE_TODAY
    assert public_state(offer(), NOW, TZ) == PublicState.ON_ORDER
    assert public_state(offer(daily_confirmed_on=DAY - timedelta(days=1)), NOW, TZ) == (
        PublicState.ON_ORDER
    )


def test_daily_without_confirmation_and_one_off_have_no_badge():
    assert public_state(offer(kind="daily"), NOW, TZ) == PublicState.NONE
    assert public_state(offer(kind="one_off"), NOW, TZ) == PublicState.NONE
    assert state_vm(PublicState.NONE) is None


def test_daily_confirmation_respects_closing_time():
    daily = offer(kind="daily", daily_confirmed_on=DAY, closing_time=time(18, 0))
    assert public_state(daily, NOW, TZ) == PublicState.AVAILABLE_TODAY
    late = datetime(2026, 11, 5, 18, 0, tzinfo=TZ)
    assert public_state(daily, late, TZ) == PublicState.NONE


def test_confirmed_recurring_expires_at_2359_and_becomes_on_order():
    o = offer(daily_confirmed_on=DAY)
    assert public_state(o, datetime(2026, 11, 5, 23, 58, 59, tzinfo=TZ), TZ) == (
        PublicState.AVAILABLE_TODAY
    )
    assert public_state(o, datetime(2026, 11, 5, 23, 59, tzinfo=TZ), TZ) == PublicState.ON_ORDER


def test_seller_state_precedence():
    old = NOW - timedelta(days=20)
    everything = offer(
        kind="one_off", hidden_at=NOW, approval="pending", status="paused", last_confirmed_at=old
    )
    assert seller_state(everything, NOW, TZ, 14) == SellerState.HIDDEN
    everything.hidden_at = None
    assert seller_state(everything, NOW, TZ, 14) == SellerState.PENDING_APPROVAL
    everything.approval = "approved"
    assert seller_state(everything, NOW, TZ, 14) == SellerState.PAUSED
    everything.status = "active"
    assert seller_state(everything, NOW, TZ, 14) == SellerState.NEEDS_CONFIRMATION
    everything.last_confirmed_at = NOW
    assert seller_state(everything, NOW, TZ, 14) == SellerState.NONE


def test_seller_state_falls_back_to_public():
    assert seller_state(offer(), NOW, TZ, 14) == SellerState.ON_ORDER
    assert seller_state(offer(status="sold_out"), NOW, TZ, 14) == SellerState.SOLD_OUT


@pytest.mark.parametrize(
    ("state", "label", "icon"),
    [
        ("available_today", "Disponível hoje", "circulo-check"),
        ("on_order", "Sob encomenda", "relogio"),
        ("sold_out", "Esgotado", "circulo-menos"),
        ("sold", "Vendido", "etiqueta-check"),
        ("paused", "Pausado", "pausa"),
        ("needs_confirmation", "Precisa de confirmação", "alerta-circulo"),
        ("pending_approval", "Aguardando aprovação", "ampulheta"),
        (SellerState.HIDDEN, "Oculto pela administração", "circulo-menos"),
    ],
)
def test_state_vm(state, label, icon):
    vm = state_vm(state)
    assert (vm.label, vm.icon) == (label, icon)
    assert vm.key == str(state)


def test_daily_sold_out_shows_badge_only_on_the_day_it_was_marked():
    """Decisão do dono: "Esgotado" da oferta do dia vale só no dia em que foi marcado."""
    marked = datetime(2026, 11, 5, 9, 0, tzinfo=TZ)
    o = offer(kind="daily", status="sold_out", status_changed_at=marked)
    assert public_state(o, NOW, TZ) == PublicState.SOLD_OUT
    assert public_state(o, datetime(2026, 11, 5, 23, 58, tzinfo=TZ), TZ) == PublicState.SOLD_OUT
    next_day = datetime(2026, 11, 6, 0, 0, tzinfo=TZ)
    assert public_state(o, next_day, TZ) == PublicState.NONE
    assert public_state(o, NOW + timedelta(days=3), TZ) == PublicState.NONE
    # O vendedor continua vendo o estado gravado.
    assert seller_state(o, next_day, TZ, 14) == SellerState.SOLD_OUT
    # Recorrente esgotada continua "Esgotado" nos dias seguintes.
    recurring = offer(status="sold_out", status_changed_at=marked)
    assert public_state(recurring, next_day, TZ) == PublicState.SOLD_OUT
