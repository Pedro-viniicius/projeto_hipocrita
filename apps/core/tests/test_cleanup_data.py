"""Comando `cleanup_data`: sessões vencidas, buscas antigas e texto de denúncias (S7)."""

from datetime import date, datetime, timedelta
from io import StringIO

import pytest
import time_machine
from django.contrib.sessions.models import Session
from django.core.management import call_command

from apps.core.models import RateLimitCounter
from apps.metrics.models import DailySearchMiss
from apps.moderation.models import Report

pytestmark = pytest.mark.django_db

# 10h em São Paulo: "hoje" é 2026-11-05 no fuso da comunidade e em UTC.
NOW = datetime.fromisoformat("2026-11-05 10:00:00-03:00")
SECRET_DETAILS = "o vendedor fulano mora na rua tal"


def run() -> str:
    out = StringIO()
    with time_machine.travel(NOW, tick=False):
        call_command("cleanup_data", stdout=out)
    return out.getvalue()


def test_deletes_search_misses_older_than_90_days():
    today = date(2026, 11, 5)
    for days in (0, 89, 90, 91, 400):
        DailySearchMiss.objects.create(date=today - timedelta(days=days), term=f"t{days}", count=1)
    run()
    kept = set(DailySearchMiss.objects.values_list("term", flat=True))
    assert kept == {"t0", "t89", "t90"}


def _report(offer, *, status, resolved_days_ago=None, details=SECRET_DETAILS):
    report = Report.objects.create(offer=offer, reason="other", details=details, status=status)
    if resolved_days_ago is not None:
        Report.objects.filter(pk=report.pk).update(
            resolved_at=NOW - timedelta(days=resolved_days_ago)
        )
    return report


def test_clears_details_of_reports_resolved_more_than_180_days_ago(make_offer):
    offer = make_offer()
    old = _report(offer, status="resolved", resolved_days_ago=181)
    recent = _report(offer, status="resolved", resolved_days_ago=179)
    still_open = _report(offer, status="open")
    Report.objects.filter(pk=still_open.pk).update(created_at=NOW - timedelta(days=400))
    run()
    old.refresh_from_db()
    recent.refresh_from_db()
    still_open.refresh_from_db()
    assert old.details == ""
    # O resto da denúncia fica (motivo, estado, datas): só o texto livre sai.
    assert (old.reason, old.status, old.resolved_at is not None) == ("other", "resolved", True)
    assert recent.details == SECRET_DETAILS
    assert still_open.details == SECRET_DETAILS


def test_clears_expired_sessions_and_old_rate_limit_rows():
    Session.objects.create(
        session_key="a" * 32, session_data="x", expire_date=NOW - timedelta(minutes=1)
    )
    Session.objects.create(
        session_key="b" * 32, session_data="x", expire_date=NOW + timedelta(days=1)
    )
    RateLimitCounter.objects.create(
        scope="login_ip", key_hash="c" * 64, window_start=NOW - timedelta(hours=25), count=1
    )
    RateLimitCounter.objects.create(
        scope="login_ip", key_hash="d" * 64, window_start=NOW - timedelta(hours=1), count=1
    )
    run()
    assert list(Session.objects.values_list("session_key", flat=True)) == ["b" * 32]
    assert list(RateLimitCounter.objects.values_list("key_hash", flat=True)) == ["d" * 64]


def test_output_has_counts_only_and_is_idempotent(make_offer):
    _report(make_offer(), status="resolved", resolved_days_ago=200)
    DailySearchMiss.objects.create(date=date(2026, 1, 1), term="nome de alguem", count=3)
    first = run()
    assert SECRET_DETAILS not in first
    assert "nome de alguem" not in first
    assert "1" in first
    second = run()
    assert "0" in second
    assert Report.objects.get().details == ""


def test_empty_database():
    assert run()
