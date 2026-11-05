"""Painel de métricas (CA16, leitura): últimos 30 dias, só tabelas, sem dado do visitante."""

from datetime import date

import pytest
import time_machine
from django.urls import reverse

from apps.core.testing import assert_accessible_page, parse_html
from apps.metrics.models import DailyOfferStat, DailySearchMiss

# 22:30 em Lavras já é dia 6 em UTC: o "hoje" do painel tem de ser 5/11.
NOW = "2026-11-05 22:30:00-03:00"
TODAY = date(2026, 11, 5)
FIRST_DAY = date(2026, 10, 7)  # hoje e os 29 dias anteriores
OUTSIDE = date(2026, 10, 6)


@pytest.fixture
def stats(make_offer, make_seller):
    bolo = make_offer(make_seller(display_name="Doces da Ana"), title="Bolo de pote")
    aula = make_offer(make_seller(display_name="Bia Aulas"), title="Aula de cálculo")
    DailyOfferStat.objects.create(date=TODAY, offer=bolo, views=10, whatsapp_clicks=2)
    DailyOfferStat.objects.create(date=FIRST_DAY, offer=bolo, views=5, whatsapp_clicks=1)
    DailyOfferStat.objects.create(date=OUTSIDE, offer=bolo, views=1000, whatsapp_clicks=900)
    DailyOfferStat.objects.create(date=TODAY, offer=aula, views=40, whatsapp_clicks=0)
    DailySearchMiss.objects.create(date=TODAY, term="bicicleta", count=3)
    DailySearchMiss.objects.create(date=FIRST_DAY, term="bicicleta", count=2)
    DailySearchMiss.objects.create(date=TODAY, term="apostila de fisica", count=7)
    DailySearchMiss.objects.create(date=OUTSIDE, term="patinete", count=99)
    return {"bolo": bolo, "aula": aula}


def _get(client):
    with time_machine.travel(NOW, tick=False):
        return client.get(reverse("metrics:dashboard"))


def _table_rows(response, caption_start: str) -> list[list[str]]:
    doc = parse_html(response)
    for table in doc.find_all("table"):
        caption = table.find("caption")
        if caption is not None and caption.text.startswith(caption_start):
            body = table.find("tbody")
            return [
                [cell.text for cell in tr.find_all() if cell.tag in {"td", "th"}]
                for tr in body.find_all("tr")
            ]
    raise AssertionError(f"tabela {caption_start!r} não encontrada")


def test_offer_table_sums_last_30_days(staff_client, stats):
    response = _get(staff_client)
    assert response.status_code == 200
    rows = _table_rows(response, "Visualizações e cliques")
    assert rows == [
        ["Aula de cálculo", "Bia Aulas", "40", "0"],
        ["Bolo de pote", "Doces da Ana", "15", "3"],
    ]
    doc = parse_html(response)
    link = reverse("moderation:offer_preview", args=[stats["bolo"].pk])
    assert doc.find("a", href=link) is not None


def test_search_misses_by_term_with_count(staff_client, stats):
    rows = _table_rows(_get(staff_client), "Buscas sem resultado")
    assert rows == [["apostila de fisica", "7"], ["bicicleta", "5"]]


def test_daily_totals(staff_client, stats):
    rows = _table_rows(_get(staff_client), "Totais por dia")
    assert rows == [
        ["05/11/2026", "50", "2", "10"],
        ["07/10/2026", "5", "1", "2"],
    ]


def test_window_uses_community_date_and_reminds_click_is_not_sale(staff_client, stats):
    response = _get(staff_client)
    html = response.content.decode()
    assert "de 07/10/2026 a 05/11/2026" in html
    assert "patinete" not in html  # termo de 31 dias atrás fica fora
    assert "intenção de contato, não venda" in html


def test_only_tables_no_chart_and_accessible(staff_client, stats):
    response = _get(staff_client)
    doc = parse_html(response)
    assert doc.find("canvas") is None
    assert not [s for s in doc.find_all("script")]
    assert len(doc.find_all("table")) == 3
    for table in doc.find_all("table"):
        assert table.find("caption") is not None
        assert all(th.get("scope") for th in table.find_all("th"))
    assert_accessible_page(response)


def test_empty_dashboard(staff_client):
    response = _get(staff_client)
    html = response.content.decode()
    assert response.status_code == 200
    assert "Nenhuma visualização nem clique no período." in html
    assert "Nenhuma busca sem resultado no período." in html
    assert parse_html(response).find("table") is None


def test_metrics_tables_have_no_visitor_columns():
    """O painel só lê contagens: as tabelas não têm IP, User-Agent, cookie nem usuário."""
    for model in (DailyOfferStat, DailySearchMiss):
        names = {field.name for field in model._meta.get_fields()}
        assert not names & {"ip", "user_agent", "cookie", "session", "user", "visitor"}
