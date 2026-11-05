"""Gravação das métricas: agregadas por dia, sem IP, User-Agent nem cookie (CA16, D15)."""

from datetime import date

import pytest
import time_machine
from django.test import RequestFactory

from apps.core.testing import assert_no_set_cookie
from apps.metrics import recording
from apps.metrics.models import DailyOfferStat, DailySearchMiss

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 5)
BROWSER = "Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile"


def test_offer_counters_are_incremented_per_day(make_offer):
    offer = make_offer()
    recording.record_offer_view(offer.pk, DAY)
    recording.record_offer_view(offer.pk, DAY)
    recording.record_whatsapp_click(offer.pk, DAY)
    recording.record_offer_view(offer.pk, date(2026, 11, 6))
    rows = {s.date: (s.views, s.whatsapp_clicks) for s in DailyOfferStat.objects.all()}
    assert rows == {DAY: (2, 1), date(2026, 11, 6): (1, 0)}


def test_increment_uses_f_expression_update(make_offer, django_assert_num_queries):
    offer = make_offer()
    recording.record_offer_view(offer.pk, DAY)
    # Linha já existe: um único UPDATE com F(), sem ler o valor antes.
    with django_assert_num_queries(1) as ctx:
        recording.record_offer_view(offer.pk, DAY)
    sql = ctx.captured_queries[0]["sql"].upper()
    assert sql.startswith("UPDATE")
    assert '"VIEWS" = ("METRICS_DAILYOFFERSTAT"."VIEWS" + 1)' in sql.replace("`", '"')


def test_search_miss_is_normalized_and_truncated():
    recording.record_search_miss("  Pão   de QUEIJO ", DAY)
    recording.record_search_miss("pao de queijo", DAY)
    recording.record_search_miss("x" * 100, DAY)
    recording.record_search_miss("   ", DAY)
    rows = {m.term: m.count for m in DailySearchMiss.objects.all()}
    assert rows == {"pao de queijo": 2, "x" * 60: 1}


def test_metric_tables_have_no_personal_columns():
    for model in (DailyOfferStat, DailySearchMiss):
        columns = {f.name for f in model._meta.get_fields()}
        assert not columns & {"ip", "ip_address", "user_agent", "cookie", "session", "user"}


@pytest.mark.parametrize(
    ("method", "agent", "expected"),
    [
        ("GET", BROWSER, True),
        ("HEAD", BROWSER, False),
        ("GET", "", False),
        ("GET", "WhatsApp/2.23.20.0 A", False),
        ("GET", "Mozilla/5.0 (compatible; bingbot/2.0)", False),
        ("GET", "Mozilla/5.0 (compatible; YandexSpider)", False),
        ("GET", "SomeCrawler/1.0", False),
        ("GET", "Mozilla/5.0 Google-PageRenderer Google (+preview)", False),
        ("GET", "facebookexternalhit/1.1", False),
    ],
)
def test_is_countable_filters_head_and_robots(method, agent, expected):
    request = getattr(RequestFactory(), method.lower())("/", headers={"user-agent": agent})
    assert recording.is_countable(request) is expected


def test_is_countable_skips_the_owner(make_user):
    owner, other = make_user(), make_user()
    request = RequestFactory().get("/", headers={"user-agent": BROWSER})
    request.user = owner
    assert recording.is_countable(request, owner_user_id=owner.pk) is False
    request.user = other
    assert recording.is_countable(request, owner_user_id=owner.pk) is True


def test_public_pages_and_redirect_set_no_cookie(client, make_offer):
    offer = make_offer(variants=[("Ninho", 800)])
    headers = {"user-agent": BROWSER}
    with time_machine.travel("2026-11-05 12:00:00-03:00", tick=False):
        paths = [
            "/",
            "/?q=nada-encontrado",
            f"/oferta/{offer.pk}/",
            f"/oferta/{offer.pk}/whatsapp/?variacao={offer.variants.get().pk}",
            f"/vendedor/{offer.seller.slug}/",
        ]
        for path in paths:
            response = client.get(path, headers=headers)
            assert response.status_code in (200, 302), path
            assert_no_set_cookie(response)
    assert not client.cookies
    stat = DailyOfferStat.objects.get()
    assert (stat.views, stat.whatsapp_clicks) == (1, 1)
    assert DailySearchMiss.objects.get().term == "nada-encontrado"


def test_search_miss_drops_control_characters():
    """Q1: NUL e outros caracteres de controle nunca vão para o banco."""
    recording.record_search_miss("a\x00b\x07c\td", DAY)
    assert DailySearchMiss.objects.get().term == "a b c d"
    recording.record_search_miss("\x00\x01", DAY)  # só controle: vazio, não grava
    assert DailySearchMiss.objects.count() == 1


def test_search_miss_caps_distinct_terms_per_day(monkeypatch):
    """S7: depois de 500 termos distintos no dia, termo novo não cria linha."""
    monkeypatch.setattr(recording, "MAX_SEARCH_TERMS_PER_DAY", 3)
    for term in ("aa", "bb", "cc", "dd"):
        recording.record_search_miss(term, DAY)
    assert set(DailySearchMiss.objects.values_list("term", flat=True)) == {"aa", "bb", "cc"}
    # Os que já existem continuam somando; outro dia tem o próprio teto.
    recording.record_search_miss("aa", DAY)
    recording.record_search_miss("dd", date(2026, 11, 6))
    assert DailySearchMiss.objects.get(date=DAY, term="aa").count == 2
    assert DailySearchMiss.objects.filter(date=date(2026, 11, 6), term="dd").exists()


def test_search_miss_cap_is_500():
    assert recording.MAX_SEARCH_TERMS_PER_DAY == 500
