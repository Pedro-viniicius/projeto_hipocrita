"""Gravação das métricas agregadas por dia (CA16, D15).

Só contagens por dia: nenhuma linha guarda IP, User-Agent, cookie, sessão ou
usuário. O User-Agent é lido apenas para decidir se a visita conta (robôs e
prévias de link não contam) e é descartado em seguida.

Os incrementos são atômicos (`F()` no `UPDATE`); se a linha do dia ainda não
existe, ela é criada, e uma corrida com outra requisição cai de volta no
`UPDATE` (mesmo padrão de `apps/core/ratelimit.py`).
"""

from collections.abc import Callable
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import F, Model
from django.http import HttpRequest

from apps.catalog.domain.search import normalize
from apps.metrics.models import DailyOfferStat, DailySearchMiss

# Pedaços de User-Agent de robôs, buscadores e prévias de link (o WhatsApp
# busca a prévia com "WhatsApp/2.x"). Comparação sem diferença de maiúsculas.
NOT_COUNTED_AGENTS = (
    "whatsapp/",
    "bot",
    "crawl",
    "spider",
    "preview",
    "facebookexternalhit",
    "slurp",
    "headless",
    "python-requests",
    "curl/",
    "wget/",
)
MAX_TERM_LENGTH = DailySearchMiss._meta.get_field("term").max_length
# Teto de termos distintos por dia (S7): depois dele, termo novo não cria linha
# (os que já existem continuam somando). Evita encher a tabela com buscas a esmo.
MAX_SEARCH_TERMS_PER_DAY = 500


def is_countable(request: HttpRequest, owner_user_id: int | None = None) -> bool:
    """A requisição conta como visita de gente: GET (HEAD não conta), com
    User-Agent de navegador e não feita pelo próprio vendedor (`owner_user_id`)."""
    if request.method != "GET":
        return False
    agent = (request.headers.get("User-Agent") or "").lower()
    if not agent or any(marker in agent for marker in NOT_COUNTED_AGENTS):
        return False
    if owner_user_id is not None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.pk == owner_user_id:
            return False
    return True


def _increment(
    model: type[Model], lookup: dict, field: str, can_create: Callable[[], bool] | None = None
) -> None:
    """Soma 1 em `field` da linha `lookup`, criando-a se `can_create` (quando dado) deixar."""
    rows = model.objects.filter(**lookup)
    if rows.update(**{field: F(field) + 1}):
        return
    if can_create is not None and not can_create():
        return
    try:
        with transaction.atomic():
            model.objects.create(**lookup, **{field: 1})
    except IntegrityError:
        # Outra requisição criou a linha do dia ao mesmo tempo.
        rows.update(**{field: F(field) + 1})


def record_offer_view(offer_id: int, day: date) -> None:
    """Soma uma visualização da página da oferta no dia."""
    _increment(DailyOfferStat, {"date": day, "offer_id": offer_id}, "views")


def record_whatsapp_click(offer_id: int, day: date) -> None:
    """Soma um clique em "Consultar no WhatsApp" no dia."""
    _increment(DailyOfferStat, {"date": day, "offer_id": offer_id}, "whatsapp_clicks")


def normalize_term(raw: str) -> str:
    """Termo como é guardado: normalizado (sem acento, minúsculo, sem caracteres de
    controle como NUL, que o PostgreSQL recusa) e com até 60 caracteres."""
    return normalize(raw)[:MAX_TERM_LENGTH].strip()


def record_search_miss(raw_term: str, day: date) -> None:
    """Soma uma busca sem resultado para o termo normalizado. Termo vazio não grava.

    Termo novo só cria linha enquanto o dia tem menos de 500 termos distintos (S7).
    """
    term = normalize_term(raw_term)
    if not term:
        return

    def below_daily_cap() -> bool:
        return DailySearchMiss.objects.filter(date=day).count() < MAX_SEARCH_TERMS_PER_DAY

    _increment(DailySearchMiss, {"date": day, "term": term}, "count", below_daily_cap)
