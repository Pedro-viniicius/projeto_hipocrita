"""Painel de métricas (`/admin/metricas/`), só leitura e só para o admin (D22).

Mostra os últimos 30 dias em tabelas: visualizações e cliques por anúncio,
totais por dia e buscas sem resultado por termo. As tabelas de métrica não têm
nada do visitante (CA16), então não há o que esconder aqui.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.core import clock
from apps.core.auth import staff_required
from apps.metrics.models import DailyOfferStat, DailySearchMiss

WINDOW_DAYS = 30
SEARCH_MISS_LIMIT = 100


@dataclass(frozen=True)
class Window:
    start: date
    end: date


def window_ending(today: date, days: int = WINDOW_DAYS) -> Window:
    """Os últimos `days` dias, contando hoje."""
    return Window(start=today - timedelta(days=days - 1), end=today)


def offer_totals(window: Window) -> list[dict]:
    """Visualizações e cliques por anúncio no período, do mais visto para o menos visto."""
    rows = (
        DailyOfferStat.objects.filter(date__range=(window.start, window.end))
        .values("offer_id", "offer__title", "offer__seller__display_name")
        .annotate(views=Sum("views"), clicks=Sum("whatsapp_clicks"))
        .order_by("-views", "-clicks", "offer__title", "offer_id")
    )
    return [
        {
            "offer_id": row["offer_id"],
            "title": row["offer__title"],
            "seller_name": row["offer__seller__display_name"],
            "views": row["views"] or 0,
            "clicks": row["clicks"] or 0,
        }
        for row in rows
    ]


def daily_totals(window: Window) -> list[dict]:
    """Totais por dia (só os dias com registro), do mais recente para o mais antigo."""
    totals: dict[date, dict] = {}

    def entry(day: date) -> dict:
        return totals.setdefault(day, {"date": day, "views": 0, "clicks": 0, "misses": 0})

    offer_rows = (
        DailyOfferStat.objects.filter(date__range=(window.start, window.end))
        .values("date")
        .annotate(views=Sum("views"), clicks=Sum("whatsapp_clicks"))
    )
    for row in offer_rows:
        item = entry(row["date"])
        item["views"] = row["views"] or 0
        item["clicks"] = row["clicks"] or 0
    miss_rows = (
        DailySearchMiss.objects.filter(date__range=(window.start, window.end))
        .values("date")
        .annotate(misses=Sum("count"))
    )
    for row in miss_rows:
        entry(row["date"])["misses"] = row["misses"] or 0
    return sorted(totals.values(), key=lambda item: item["date"], reverse=True)


def search_miss_totals(window: Window) -> list[dict]:
    """Buscas sem resultado por termo no período, da mais frequente para a menos."""
    rows = (
        DailySearchMiss.objects.filter(date__range=(window.start, window.end))
        .values("term")
        .annotate(total=Sum("count"))
        .order_by("-total", "term")[:SEARCH_MISS_LIMIT]
    )
    return [{"term": row["term"], "count": row["total"] or 0} for row in rows]


@never_cache
@staff_required
@require_safe
def dashboard(request: HttpRequest) -> HttpResponse:
    today = clock.now().astimezone(clock.community_tz()).date()
    window = window_ending(today)
    context = {
        "window": window,
        "window_days": WINDOW_DAYS,
        "offer_rows": offer_totals(window),
        "daily_rows": daily_totals(window),
        "miss_rows": search_miss_totals(window),
        "miss_limit": SEARCH_MISS_LIMIT,
        "active_tab": "metrics",
    }
    return render(request, "metrics/dashboard.html", context)
