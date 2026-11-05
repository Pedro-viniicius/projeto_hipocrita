"""CA9 e CA10: expiração da confirmação do dia e da venda pontual (relógio injetado)."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.catalog.domain.availability import (
    can_contact,
    daily_expires_at,
    has_public_contact,
    is_available_today,
    is_listed,
    is_page_visible,
    needs_reconfirmation,
)

TZ = ZoneInfo("America/Sao_Paulo")
DAY = date(2026, 11, 5)


def at(h, m=0, s=0, day=DAY):
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=TZ)


def test_confirmation_valid_until_2359():
    assert is_available_today(DAY, None, at(23, 58, 59), TZ)
    assert not is_available_today(DAY, None, at(23, 59, 0), TZ)


def test_confirmation_does_not_carry_to_next_day():
    assert not is_available_today(DAY, None, at(0, 0, 0, DAY + timedelta(days=1)), TZ)
    assert not is_available_today(None, None, at(10), TZ)


def test_closing_time_comes_first():
    closing = time(14, 0)
    assert is_available_today(DAY, closing, at(13, 59), TZ)
    assert not is_available_today(DAY, closing, at(14, 0), TZ)


def test_closing_time_after_2359_is_capped():
    assert daily_expires_at(DAY, time(23, 59, 30), TZ) == at(23, 59)


def test_day_is_local_not_utc():
    # 21:30 em Brasília = 00:30 UTC do dia seguinte: ainda é o mesmo dia local.
    now = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)
    assert is_available_today(DAY, None, now, TZ)
    # 02:30 UTC = 23:30 locais do mesmo dia; 03:00 UTC = 00:00 locais do dia seguinte.
    assert is_available_today(DAY, None, datetime(2026, 11, 6, 2, 30, tzinfo=UTC), TZ)
    assert not is_available_today(DAY, None, datetime(2026, 11, 6, 3, 0, tzinfo=UTC), TZ)


def test_reconfirmation_after_14_days():
    last = at(10)
    assert not needs_reconfirmation(last, last + timedelta(days=13, hours=23), 14)
    assert needs_reconfirmation(last, last + timedelta(days=14), 14)


def offer(**kw):
    seller = SimpleNamespace(
        is_demo=False,
        whatsapp_public=True,
        whatsapp_number="5535912345678",
        user=SimpleNamespace(is_active=True),
    )
    base = dict(
        seller=seller,
        approval="approved",
        hidden_at=None,
        status="active",
        kind="recurring",
        last_confirmed_at=at(9),
        status_changed_at=at(9),
    )
    base.update(kw)
    return SimpleNamespace(**base)


NOW = at(12)


def vis(o):
    return is_page_visible(o, NOW, TZ, 14)


def test_visible_by_default():
    assert vis(offer())
    assert can_contact(offer(), NOW, TZ, 14)


@pytest.mark.parametrize(
    "change",
    [
        {"approval": "pending"},
        {"hidden_at": at(8)},
        {"status": "paused"},
    ],
)
def test_not_visible(change):
    assert not vis(offer(**change))


def test_inactive_account_and_missing_contact():
    o = offer()
    o.seller.user.is_active = False
    assert not vis(o)
    o = offer()
    o.seller.whatsapp_public = False
    assert not vis(o)
    o = offer()
    o.seller.whatsapp_number = ""
    assert not vis(o)


def test_demo_seller_has_contact_without_number():
    o = offer()
    o.seller.is_demo, o.seller.whatsapp_public, o.seller.whatsapp_number = True, False, ""
    assert has_public_contact(o.seller, demo_enabled=True)
    assert is_page_visible(o, NOW, TZ, 14, demo_enabled=True)


def test_demo_seller_is_not_public_when_demo_data_is_off():
    """R3: com DEMO_DATA desligado, a demonstração sai da vitrine (o padrão é o seguro)."""
    o = offer()
    o.seller.is_demo, o.seller.whatsapp_public, o.seller.whatsapp_number = True, False, ""
    assert not has_public_contact(o.seller)
    assert not has_public_contact(o.seller, demo_enabled=False)
    assert not is_page_visible(o, NOW, TZ, 14, demo_enabled=False)
    assert not is_listed(o, NOW, TZ, 14)
    assert not can_contact(o, NOW, TZ, 14, demo_enabled=False)


def test_one_off_expires_but_recurring_does_not():
    old = NOW - timedelta(days=14)
    assert not vis(offer(kind="one_off", last_confirmed_at=old))
    assert vis(offer(kind="one_off", last_confirmed_at=NOW - timedelta(days=13, hours=23)))
    assert vis(offer(kind="recurring", last_confirmed_at=old))


def test_sold_stays_listed_until_end_of_sale_day_but_page_stays():
    sold = offer(kind="one_off", status="sold", status_changed_at=at(9))
    assert is_listed(sold, at(23, 58), TZ, 14)
    assert not is_listed(sold, at(23, 59), TZ, 14)
    assert not is_listed(sold, at(1, 0, day=DAY + timedelta(days=1)), TZ, 14)
    assert is_page_visible(sold, at(1, 0, day=DAY + timedelta(days=1)), TZ, 14)
    assert not can_contact(sold, NOW, TZ, 14)


def test_sold_out_listed_but_no_contact():
    o = offer(status="sold_out")
    assert is_listed(o, NOW, TZ, 14)
    assert not can_contact(o, NOW, TZ, 14)


def test_paused_not_listed():
    assert not is_listed(offer(status="paused"), NOW, TZ, 14)
