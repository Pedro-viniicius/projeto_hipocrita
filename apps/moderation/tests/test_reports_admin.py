"""Denúncias na administração (CA12): abertas primeiro, tratar e ocultar na mesma ação."""

from datetime import timedelta

import pytest
import time_machine
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.core import clock
from apps.core.testing import assert_accessible_page, parse_html
from apps.moderation.models import Report
from texts import moderation as texts

NOW = "2026-11-05 10:00:00-03:00"


@pytest.fixture
def offer(make_offer):
    return make_offer(title="Bolo de pote")


def _report(offer, *, reason=Report.Reason.MISLEADING, details="", age_days=0, **fields):
    report = Report.objects.create(offer=offer, reason=reason, details=details, **fields)
    if age_days:
        Report.objects.filter(pk=report.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
    return report


def _row_ids(response) -> list[int]:
    return [
        int(tr.get("id").removeprefix("denuncia-"))
        for tr in parse_html(response).find_all("tr")
        if (tr.get("id") or "").startswith("denuncia-")
    ]


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def test_open_reports_first_oldest_on_top(staff_client, offer, make_user):
    resolver = make_user(is_staff=True)
    resolved = _report(
        offer,
        status=Report.Status.RESOLVED,
        resolved_at=timezone.now(),
        resolved_by=resolver,
    )
    newer_open = _report(offer, age_days=1)
    older_open = _report(offer, age_days=3)

    response = staff_client.get(reverse("moderation:reports"))

    assert response.status_code == 200
    assert _row_ids(response) == [older_open.pk, newer_open.pk, resolved.pk]
    assert "Nenhuma denúncia aberta." not in response.content.decode()
    assert_accessible_page(response)


def test_report_row_shows_reason_details_and_offer_link(staff_client, offer):
    report = _report(offer, reason=Report.Reason.PROHIBITED, details="Vende remédio controlado")
    response = staff_client.get(reverse("moderation:reports"))
    html = response.content.decode()
    doc = parse_html(response)
    row = doc.find("tr", id=f"denuncia-{report.pk}")

    assert texts.REPORT_REASONS["prohibited"] in row.text
    assert "Vende remédio controlado" in row.text
    assert "Aberta" in row.text
    assert row.find("a", href=reverse("moderation:offer_preview", args=[offer.pk]))
    assert row.find("form", action=reverse("moderation:report_resolve", args=[report.pk]))
    assert "Ocultar anúncio" in html
    assert "Marcar como tratada" in html


def test_visitor_text_is_escaped(staff_client, offer):
    _report(offer, details='<script>alert("x")</script><b>oi</b>')
    response = staff_client.get(reverse("moderation:reports"))
    html = response.content.decode()
    assert "<script>alert" not in html
    assert "<b>oi</b>" not in html
    assert "&lt;script&gt;" in html


def test_empty_state_when_nothing_open(staff_client, offer, make_user):
    _report(
        offer,
        status=Report.Status.RESOLVED,
        resolved_at=timezone.now(),
        resolved_by=make_user(is_staff=True),
    )
    response = staff_client.get(reverse("moderation:reports"))
    html = response.content.decode()
    assert "Nenhuma denúncia aberta." in html
    assert "Tratada" in html


def test_resolve_marks_resolved_by_admin(staff_client, offer):
    report = _report(offer)
    with time_machine.travel(NOW, tick=False):
        response = staff_client.post(reverse("moderation:report_resolve", args=[report.pk]))
        expected = clock.now()

    assert response.status_code == 302
    assert response["Location"] == reverse("moderation:reports")
    report.refresh_from_db()
    assert report.status == Report.Status.RESOLVED
    assert report.resolved_at == expected
    assert report.resolved_by == staff_client.user
    offer.refresh_from_db()
    assert offer.hidden_at is None
    assert texts.REPORT_RESOLVED in _messages(response)


def test_resolve_and_hide_in_one_action(staff_client, offer):
    report = _report(offer, reason=Report.Reason.OFFENSIVE)
    with time_machine.travel(NOW, tick=False):
        response = staff_client.post(
            reverse("moderation:report_resolve", args=[report.pk]), {"hide": "1"}
        )
        expected = clock.now()

    report.refresh_from_db()
    offer.refresh_from_db()
    assert report.status == Report.Status.RESOLVED
    assert report.resolved_by == staff_client.user
    assert offer.hidden_at == expected
    assert offer.hidden_reason == texts.HIDE_REASON_FROM_REPORT.format(
        reason=texts.REPORT_REASONS["offensive"]
    )
    assert texts.REPORT_RESOLVED_AND_HIDDEN in _messages(response)


def test_resolving_again_keeps_first_resolution(staff_client, offer, make_user):
    first_admin = make_user(is_staff=True)
    when = timezone.now() - timedelta(days=1)
    report = _report(
        offer, status=Report.Status.RESOLVED, resolved_at=when, resolved_by=first_admin
    )
    staff_client.post(reverse("moderation:report_resolve", args=[report.pk]))
    report.refresh_from_db()
    assert report.resolved_by == first_admin
    assert report.resolved_at == when


def test_resolved_row_has_no_actions(staff_client, offer, make_user):
    report = _report(
        offer,
        status=Report.Status.RESOLVED,
        resolved_at=timezone.now(),
        resolved_by=make_user(is_staff=True),
    )
    row = parse_html(staff_client.get(reverse("moderation:reports"))).find(
        "tr", id=f"denuncia-{report.pk}"
    )
    assert row.find("form") is None
    assert "Tratada em" in row.text


def test_hidden_offer_row_only_offers_resolve(staff_client, make_offer):
    offer = make_offer(hidden_at=timezone.now())
    report = _report(offer)
    row = parse_html(staff_client.get(reverse("moderation:reports"))).find(
        "tr", id=f"denuncia-{report.pk}"
    )
    forms = row.find_all("form")
    assert len(forms) == 1
    assert forms[0].find("input", name="hide") is None
    assert "Anúncio oculto" in row.text
