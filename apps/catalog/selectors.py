"""Consultas da vitrine pública.

O banco faz o filtro grosso (aprovado, não oculto, conta ativa, contato
público, não pausado, categoria). O que depende do relógio (disponível hoje,
vendido hoje, venda pontual vencida), a busca e o rodízio ficam em Python,
nas funções puras de `domain/`, com `now` e `tz` injetados.

Anúncio e vendedor de demonstração só são públicos com `settings.DEMO_DATA`
ligado: o selector lê a configuração e a passa ao domínio (`demo_enabled`).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q, QuerySet

from apps.catalog.domain.availability import is_listed
from apps.catalog.domain.ordering import order_offers
from apps.catalog.domain.search import match_tier, split_terms
from apps.catalog.domain.states import PublicState, public_state
from apps.catalog.models import Category, Offer, Seller


def public_contact_q(prefix: str = "") -> Q:
    """Mesmo critério de `domain.availability.has_public_contact`, no banco.

    A demonstração só entra com `settings.DEMO_DATA` ligado.
    """
    real = Q(**{f"{prefix}whatsapp_public": True}) & ~Q(**{f"{prefix}whatsapp_number": ""})
    if settings.DEMO_DATA:
        return Q(**{f"{prefix}is_demo": True}) | real
    return real


def public_candidates(
    category: Category | None = None, seller: Seller | None = None
) -> QuerySet[Offer]:
    """Anúncios que podem aparecer ao público, antes das regras de tempo."""
    qs = (
        Offer.objects.filter(
            approval=Offer.Approval.APPROVED,
            hidden_at__isnull=True,
            seller__user__is_active=True,
        )
        .filter(public_contact_q("seller__"))
        .exclude(status=Offer.Status.PAUSED)
        .select_related("seller__user", "category")
        .prefetch_related("variants", "photos")
    )
    if category is not None:
        qs = qs.filter(category=category)
    if seller is not None:
        qs = qs.filter(seller=seller)
    return qs


def active_categories() -> list[Category]:
    return list(Category.objects.filter(is_active=True))


def public_seller(slug: str) -> Seller | None:
    """Vendedor com página pública: conta ativa e contato público."""
    return (
        Seller.objects.filter(public_contact_q(), slug=slug, user__is_active=True)
        .select_related("user")
        .first()
    )


def visible_offer(pk: int) -> Offer | None:
    """Anúncio pelo id, com o que a página precisa (a visibilidade é decidida em `domain`)."""
    return (
        Offer.objects.filter(pk=pk)
        .select_related("seller__user", "category")
        .prefetch_related("variants", "photos")
        .first()
    )


def _search_body(offer: Offer) -> str:
    """Texto secundário da busca: descrição, variações e categoria (D13)."""
    names = " ".join(v.name for v in offer.variants.all())
    return f"{offer.description} {names} {offer.category.name}"


def list_offers(
    candidates: QuerySet[Offer],
    *,
    q: str,
    today_only: bool,
    now: datetime,
    tz: ZoneInfo,
    days: int,
) -> list[Offer]:
    """Ofertas compatíveis, já na ordem do rodízio: aplica disponibilidade,
    "Disponíveis hoje", busca e semente do dia (CA1, CA17)."""
    terms = split_terms(q)
    items: list[tuple[int | None, Offer]] = []
    for offer in candidates:
        if not is_listed(offer, now, tz, days, demo_enabled=settings.DEMO_DATA):
            continue
        if today_only and public_state(offer, now, tz) != PublicState.AVAILABLE_TODAY:
            continue
        tier = match_tier(terms, offer.title, offer.seller.display_name, _search_body(offer))
        if tier is None:
            continue
        items.append((tier, offer))
    day = now.astimezone(tz).date()
    return order_offers(items, day)
