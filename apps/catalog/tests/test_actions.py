"""Ações do vendedor (CA7) e confirmações (CA9, CA10)."""

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.catalog.domain.actions import (
    ACTIONS,
    ActionNotAllowed,
    allowed_actions,
    apply_action,
    confirmation_refusal,
)

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=TZ)
OLD = NOW - timedelta(days=20)


def offer(**kw):
    base = dict(
        kind="recurring",
        status="active",
        hidden_at=None,
        daily_confirmed_on=None,
        closing_time=None,
        last_confirmed_at=OLD,
        status_changed_at=OLD,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_allowed_actions_by_kind_and_status():
    assert allowed_actions(offer(), NOW, TZ, 14) == ["confirm_today", "sold_out", "pause"]
    assert allowed_actions(offer(status="sold_out"), NOW, TZ, 14) == [
        "confirm_today",
        "restock",
        "pause",
    ]
    assert allowed_actions(offer(status="paused"), NOW, TZ, 14) == ["confirm_today", "resume"]
    assert allowed_actions(offer(kind="one_off"), NOW, TZ, 14) == ["reconfirm", "sold", "pause"]
    assert allowed_actions(offer(kind="one_off", status="sold"), NOW, TZ, 14) == ["unsold"]
    assert allowed_actions(offer(hidden_at=NOW), NOW, TZ, 14) == []


def test_reconfirm_offered_only_when_needed():
    fresh = offer(kind="one_off", last_confirmed_at=NOW - timedelta(days=13, hours=23))
    assert "reconfirm" not in allowed_actions(fresh, NOW, TZ, 14)
    assert "reconfirm" in allowed_actions(offer(kind="one_off"), NOW, TZ, 14)


def test_confirm_hidden_once_confirmed_today():
    o = offer(daily_confirmed_on=NOW.date())
    assert "confirm_today" not in allowed_actions(o, NOW, TZ, 14)


def test_reconfirm_renews_one_off():
    o = offer(kind="one_off")
    apply_action(o, "reconfirm", NOW, TZ)
    assert o.last_confirmed_at == NOW
    assert o.status == "active"


def test_resume_and_unsold_renew_one_off_only():
    paused = offer(kind="one_off", status="paused")
    apply_action(paused, "resume", NOW, TZ)
    assert (paused.status, paused.last_confirmed_at, paused.status_changed_at) == (
        "active",
        NOW,
        NOW,
    )
    sold = offer(kind="one_off", status="sold")
    apply_action(sold, "unsold", NOW, TZ)
    assert (sold.status, sold.last_confirmed_at) == ("active", NOW)
    rec = offer(status="paused")
    apply_action(rec, "resume", NOW, TZ)
    assert rec.last_confirmed_at == OLD


def test_status_actions():
    o = offer()
    apply_action(o, "sold_out", NOW, TZ)
    assert (o.status, o.status_changed_at) == ("sold_out", NOW)
    apply_action(o, "restock", NOW, TZ)
    assert o.status == "active"
    apply_action(o, "pause", NOW, TZ)
    assert o.status == "paused"
    one = offer(kind="one_off")
    apply_action(one, "sold", NOW, TZ)
    assert one.status == "sold"


def test_confirm_today_sets_day_and_activates():
    o = offer(status="sold_out")
    apply_action(o, "confirm_today", NOW, TZ)
    assert o.daily_confirmed_on == NOW.date()
    assert o.status == "active"


def test_confirm_today_for_daily_with_closing_time():
    o = offer(kind="daily")
    apply_action(o, "confirm_today", NOW, TZ, closing_time=time(18, 0))
    assert (o.daily_confirmed_on, o.closing_time) == (NOW.date(), time(18, 0))


@pytest.mark.parametrize("closing", [time(12, 0), time(11, 59)])
def test_confirm_today_refused_after_closing(closing):
    o = offer(kind="daily")
    with pytest.raises(ActionNotAllowed) as exc:
        apply_action(o, "confirm_today", NOW, TZ, closing_time=closing)
    assert exc.value.reason == "closing_passed"
    assert o.daily_confirmed_on is None


def test_confirm_today_refused_with_saved_closing_time_passed():
    o = offer(kind="daily", closing_time=time(10, 0))
    with pytest.raises(ActionNotAllowed):
        apply_action(o, "confirm_today", NOW, TZ)


def test_recurring_ignores_closing_time():
    o = offer()
    apply_action(o, "confirm_today", NOW, TZ, closing_time=time(8, 0))
    assert o.daily_confirmed_on == NOW.date()
    assert o.closing_time is None


@pytest.mark.parametrize(
    ("kwargs", "action"),
    [
        ({"kind": "one_off"}, "confirm_today"),
        ({"kind": "one_off"}, "sold_out"),
        ({}, "sold"),
        ({}, "resume"),
        ({"status": "paused"}, "pause"),
        ({"hidden_at": NOW}, "pause"),
        ({}, "inexistente"),
    ],
)
def test_not_allowed(kwargs, action):
    o = offer(**kwargs)
    before = vars(o).copy()
    with pytest.raises(ActionNotAllowed):
        apply_action(o, action, NOW, TZ)
    assert vars(o) == before


def test_actions_constant():
    assert {
        "pause", "resume", "sold_out", "restock", "sold", "unsold", "confirm_today", "reconfirm",
    } == ACTIONS  # fmt: skip


# Regra pura da confirmação (R1, R4) ------------------------------------------------


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 11, 5, hour, minute, second, tzinfo=TZ)


def test_confirmation_refusal_rules():
    assert confirmation_refusal(None, at(12, 0), TZ) is None
    assert confirmation_refusal(time(18, 0), at(17, 59), TZ) is None
    assert confirmation_refusal(time(18, 0), at(18, 0), TZ) == "closing_passed"
    assert confirmation_refusal(None, at(23, 58, 59), TZ) is None
    # A partir de 23:59 toda confirmação do dia já acabou: confirmar não teria efeito.
    assert confirmation_refusal(None, at(23, 59), TZ) == "day_over"
    assert confirmation_refusal(time(23, 59, 30), at(23, 59, 10), TZ) == "day_over"


def test_confirmation_refusal_uses_community_timezone():
    # 02:30 UTC de 6/11 = 23:30 de 5/11 em São Paulo: ainda dá; 02:59 UTC = 23:59: não dá.
    utc = ZoneInfo("UTC")
    assert confirmation_refusal(None, datetime(2026, 11, 6, 2, 30, tzinfo=utc), TZ) is None
    assert confirmation_refusal(None, datetime(2026, 11, 6, 2, 59, tzinfo=utc), TZ) == "day_over"


@pytest.mark.parametrize("kind", ["recurring", "daily"])
def test_confirm_today_refused_from_2359(kind):
    o = offer(kind=kind, status="sold_out")
    with pytest.raises(ActionNotAllowed) as exc:
        apply_action(o, "confirm_today", at(23, 59), TZ)
    assert exc.value.reason == "day_over"
    assert o.daily_confirmed_on is None
    assert o.status == "sold_out"  # nada mudou
    apply_action(o, "confirm_today", at(23, 58), TZ)
    assert o.daily_confirmed_on == NOW.date()
