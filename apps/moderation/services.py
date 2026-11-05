"""Regras da administração: aprovar, ocultar, mostrar, tratar denúncia e categorias.

As views só chamam estas funções; a autorização (`staff_required`) fica nelas.
O log registra só ids (anúncio, denúncia, categoria e admin), nunca texto livre
de denúncia, nome de vendedor ou contato.
"""

import logging
from datetime import datetime

from django.db import transaction

from apps.catalog.domain.search import normalize, split_terms
from apps.catalog.models import Category, Offer, Seller
from apps.core.text import unique_slug
from apps.moderation.models import Report
from texts import moderation as texts

logger = logging.getLogger(__name__)

# Lista de anúncios da administração: os mais recentes até este limite.
OFFER_LIST_LIMIT = 200
# Denúncias já tratadas mostradas abaixo das abertas.
RESOLVED_REPORTS_LIMIT = 50


# Anúncios --------------------------------------------------------------------


def pending_offers():
    """Fila de aprovação: anúncios aguardando aprovação e não ocultos, mais antigos primeiro."""
    return (
        Offer.objects.filter(approval=Offer.Approval.PENDING, hidden_at__isnull=True)
        .select_related("seller", "category")
        .prefetch_related("photos", "variants")
        .order_by("created_at", "pk")
    )


def search_offers(q: str) -> list[Offer]:
    """Anúncios mais recentes primeiro; com `q`, só os que têm todos os termos no título
    ou no nome do vendedor (sem acento e sem diferença de maiúsculas)."""
    qs = Offer.objects.select_related("seller", "category").order_by("-created_at", "-pk")
    terms = split_terms(q)
    if not terms:
        return list(qs[:OFFER_LIST_LIMIT])
    found = []
    for offer in qs.iterator():
        haystack = normalize(f"{offer.title} {offer.seller.display_name}")
        if all(term in haystack for term in terms):
            found.append(offer)
            if len(found) >= OFFER_LIST_LIMIT:
                break
    return found


def approve_offer(offer_pk: int, *, by, now: datetime) -> Offer:
    """Aprova o anúncio e marca o vendedor como confiável (D12)."""
    with transaction.atomic():
        offer = Offer.objects.select_for_update().get(pk=offer_pk)
        if offer.approval != Offer.Approval.APPROVED:
            offer.approval = Offer.Approval.APPROVED
            offer.approved_at = now
            offer.save(update_fields=["approval", "approved_at", "updated_at"])
        Seller.objects.filter(pk=offer.seller_id).update(is_trusted=True)
    logger.info("anúncio %s aprovado pelo admin %s", offer.pk, by.pk)
    return offer


def _hide(offer: Offer, reason: str, now: datetime) -> None:
    offer.hidden_at = now
    offer.hidden_reason = (reason or "").strip()[:200]
    offer.save(update_fields=["hidden_at", "hidden_reason", "updated_at"])


def hide_offer(offer_pk: int, reason: str, *, by, now: datetime) -> Offer:
    """Tira o anúncio da vitrine (D11: 404 público) guardando quando e por quê."""
    with transaction.atomic():
        offer = Offer.objects.select_for_update().get(pk=offer_pk)
        _hide(offer, reason, now)
    logger.info("anúncio %s ocultado pelo admin %s", offer.pk, by.pk)
    return offer


def show_offer(offer_pk: int, *, by) -> Offer:
    """Desfaz o ocultar: limpa `hidden_at` e `hidden_reason`."""
    with transaction.atomic():
        offer = Offer.objects.select_for_update().get(pk=offer_pk)
        offer.hidden_at = None
        offer.hidden_reason = ""
        offer.save(update_fields=["hidden_at", "hidden_reason", "updated_at"])
    logger.info("anúncio %s visível de novo pelo admin %s", offer.pk, by.pk)
    return offer


# Denúncias -------------------------------------------------------------------


def reports_for_admin() -> list[Report]:
    """Abertas primeiro (mais antigas no topo); depois as últimas tratadas."""
    base = Report.objects.select_related("offer", "offer__seller")
    open_reports = list(base.filter(status=Report.Status.OPEN).order_by("created_at", "pk"))
    resolved = list(
        base.filter(status=Report.Status.RESOLVED).order_by("-resolved_at", "-pk")[
            :RESOLVED_REPORTS_LIMIT
        ]
    )
    return open_reports + resolved


def resolve_report(report_pk: int, *, by, now: datetime, hide: bool = False) -> Report:
    """Marca a denúncia como tratada e, se `hide`, oculta o anúncio na mesma transação.

    Denúncia já tratada mantém quem e quando tratou; o `hide` ainda vale.
    """
    with transaction.atomic():
        report = Report.objects.select_for_update().get(pk=report_pk)
        if report.status != Report.Status.RESOLVED:
            report.status = Report.Status.RESOLVED
            report.resolved_at = now
            report.resolved_by = by
            report.save(update_fields=["status", "resolved_at", "resolved_by"])
        if hide:
            offer = Offer.objects.select_for_update().get(pk=report.offer_id)
            label = texts.REPORT_REASONS.get(report.reason, report.reason)
            _hide(offer, texts.HIDE_REASON_FROM_REPORT.format(reason=label), now)
    logger.info(
        "denúncia %s tratada pelo admin %s%s",
        report.pk,
        by.pk,
        " (anúncio ocultado)" if hide else "",
    )
    return report


# Categorias ------------------------------------------------------------------


def next_category_position() -> int:
    """Posição para a nova categoria: depois da última."""
    last = Category.objects.order_by("-position").values_list("position", flat=True).first()
    return 0 if last is None else last + 1


def create_category(*, name: str, position: int | None, is_food: bool, by) -> Category:
    if position is None:
        position = next_category_position()
    with transaction.atomic():  # ponto de retorno: a view trata o IntegrityError de nome repetido
        category = Category.objects.create(
            name=name,
            slug=unique_slug(Category, name, fallback="categoria"),
            position=position,
            is_food=is_food,
            is_active=True,
        )
    logger.info("categoria %s criada pelo admin %s", category.pk, by.pk)
    return category


def update_category(category: Category, *, name: str, position: int, is_food: bool, by) -> None:
    """Renomeia e reordena. O slug não muda, para não quebrar links já compartilhados."""
    category.name = name
    category.position = position
    category.is_food = is_food
    with transaction.atomic():  # ponto de retorno: a view trata o IntegrityError de nome repetido
        category.save(update_fields=["name", "position", "is_food"])
    logger.info("categoria %s alterada pelo admin %s", category.pk, by.pk)


def set_category_active(category: Category, active: bool, *, by) -> None:
    category.is_active = active
    category.save(update_fields=["is_active"])
    logger.info(
        "categoria %s %s pelo admin %s", category.pk, "mostrada" if active else "escondida", by.pk
    )
