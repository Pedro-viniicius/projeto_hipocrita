"""Serviços da área do vendedor: busca do próprio anúncio, painel, ações, gravação e perfil.

Autorização (CA11): todo anúncio da área do vendedor vem de `get_own_offer`, que
filtra pelo dono **na consulta**; anúncio de outro vendedor dá 404 e nada é gravado.
As regras de estado e de tempo ficam em `domain/`; aqui só se lê e grava.
"""

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from apps.catalog.domain.actions import ActionNotAllowed, allowed_actions, apply_action
from apps.catalog.domain.availability import has_public_contact, is_available_today
from apps.catalog.domain.pricing import display_price
from apps.catalog.domain.states import SellerState, StateVM, seller_state, state_vm
from apps.catalog.models import Offer, OfferPhoto, OfferVariant, Seller
from apps.catalog.photos import save_offer_photos
from apps.core import ratelimit
from apps.core.text import unique_slug
from texts import seller as texts

# Limite de envio de fotos por usuário (CA14, S1): 20 arquivos por hora para
# vendedor confiável e 12 para quem ainda não teve anúncio aprovado. A contagem
# acontece antes de decodificar, então reenvio por erro no formulário também conta:
# 12 deixa o vendedor novo reenviar 3 fotos algumas vezes e ainda publicar.
PHOTOS_SCOPE = "photos"
PHOTOS_LIMIT = 20
PHOTOS_LIMIT_UNTRUSTED = 12
PHOTOS_WINDOW_S = 60 * 60

# Teto de anúncios por vendedor (S1): no máximo 30 no total e, para quem ainda não
# é confiável, no máximo 3 aguardando aprovação.
MAX_OFFERS_PER_SELLER = 30
MAX_PENDING_UNTRUSTED = 3

# Ações que aparecem como botão próprio (fora do menu "Mais ações").
PRIMARY_ACTIONS = ("confirm_today", "reconfirm")
_ACTION_FIELDS = [
    "status",
    "status_changed_at",
    "daily_confirmed_on",
    "closing_time",
    "last_confirmed_at",
    "updated_at",
]


# Autorização -----------------------------------------------------------------


def get_own_offer(request: HttpRequest, pk: int, *, lock: bool = False) -> Offer:
    """Anúncio `pk` do usuário logado, ou 404 (também para anúncio de outro vendedor).

    Com `lock=True`, trava a linha até o fim da transação (use dentro de `atomic`).
    """
    queryset = Offer.objects.select_related("seller", "category")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    return get_object_or_404(queryset, pk=pk, seller__user=request.user)


# Painel ------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionItem:
    key: str
    label: str


@dataclass(frozen=True)
class DashboardItem:
    offer: Offer
    anchor_id: str
    state: StateVM | None
    kind_label: str
    note: str
    price_cents: int
    price_from: bool
    photo: OfferPhoto | None
    primary: ActionItem | None
    menu: list[ActionItem] = field(default_factory=list)


def _closing_label(offer: Offer) -> str:
    if offer.kind == Offer.Kind.DAILY and offer.closing_time is not None:
        return offer.closing_time.strftime("%H:%M")
    return texts.CONFIRMED_UNTIL_END_OF_DAY


def _note(offer: Offer, now: datetime, tz: ZoneInfo) -> str:
    """ "Confirmado até 23h59" / "Última confirmação há 12 dias", quando é relevante."""
    if offer.status != Offer.Status.ACTIVE:
        return ""
    if offer.kind == Offer.Kind.ONE_OFF:
        days = (now - offer.last_confirmed_at).days
        if days <= 0:
            return texts.LAST_CONFIRMATION_TODAY
        if days == 1:
            return texts.LAST_CONFIRMATION_ONE_DAY
        return texts.LAST_CONFIRMATION_DAYS.format(n=days)
    closing = offer.closing_time if offer.kind == Offer.Kind.DAILY else None
    if is_available_today(offer.daily_confirmed_on, closing, now, tz):
        return texts.CONFIRMED_UNTIL.format(hora=_closing_label(offer))
    return ""


def offer_actions(offer: Offer, now: datetime, tz: ZoneInfo, days: int) -> list[str]:
    """Ações oferecidas agora. Anúncio aguardando aprovação só pode ser editado (spec 3.6)."""
    if offer.approval != Offer.Approval.APPROVED:
        return []
    return allowed_actions(offer, now, tz, days)


def dashboard_items(seller: Seller, now: datetime, tz: ZoneInfo, days: int) -> list[DashboardItem]:
    offers = (
        seller.offers.select_related("category")
        .prefetch_related("variants", "photos")
        .order_by("-created_at", "-pk")
    )
    items = []
    for offer in offers:
        actions = [
            ActionItem(key, texts.ACTION_LABELS[key]) for key in offer_actions(offer, now, tz, days)
        ]
        primary = next((a for a in actions if a.key in PRIMARY_ACTIONS), None)
        cents, price_from = display_price(
            offer.price_cents, [v.price_cents for v in offer.variants.all()]
        )
        photos = list(offer.photos.all())
        items.append(
            DashboardItem(
                offer=offer,
                anchor_id=f"anuncio-{offer.pk}",
                state=state_vm(seller_state(offer, now, tz, days)),
                kind_label=texts.KIND_LABELS[offer.kind],
                note=_note(offer, now, tz),
                price_cents=cents,
                price_from=price_from,
                photo=photos[0] if photos else None,
                primary=primary,
                menu=[a for a in actions if a is not primary],
            )
        )
    return items


def has_pending(items: list[DashboardItem]) -> bool:
    return any(
        item.state is not None and item.state.key == SellerState.PENDING_APPROVAL for item in items
    )


def contact_is_public(seller: Seller) -> bool:
    """D4: sem WhatsApp liberado, nenhum anúncio do vendedor fica público."""
    return has_public_contact(seller, demo_enabled=settings.DEMO_DATA)


# Ações -------------------------------------------------------------------------


def run_action(
    request: HttpRequest, pk: int, action: str, now: datetime, tz: ZoneInfo, days: int
) -> Offer:
    """Aplica `action` no anúncio do usuário e grava. 404 se o anúncio não é dele.

    Levanta `ActionNotAllowed` (nada é gravado) se a ação não vale agora.
    """
    with transaction.atomic():
        offer = get_own_offer(request, pk, lock=True)
        if action not in offer_actions(offer, now, tz, days):
            reason = "pending" if offer.approval != Offer.Approval.APPROVED else "wrong_state"
            raise ActionNotAllowed(action, reason)
        apply_action(offer, action, now, tz)
        offer.save(update_fields=_ACTION_FIELDS)
    return offer


def action_message(offer: Offer, action: str) -> str:
    return texts.ACTION_DONE[action].format(titulo=offer.title)


def action_error_message(exc: ActionNotAllowed) -> str:
    if exc.reason == "closing_passed":
        return texts.ACTION_CLOSING_PASSED
    if exc.reason == "day_over":
        return texts.ACTION_DAY_OVER
    return texts.ACTION_NOT_ALLOWED


# Criar e editar ------------------------------------------------------------------


def _apply_fields(offer: Offer, data: dict, now: datetime, tz: ZoneInfo) -> None:
    """Copia os campos do formulário. Os que não valem já chegam zerados (forms_seller)."""
    previous_kind = offer.kind
    offer.kind = data["kind"]
    offer.title = data["title"]
    offer.category = data["category"]
    offer.price_cents = data["price"]
    offer.description = data["description"]
    offer.fulfillment = data["fulfillment"]
    offer.portion = data["portion"]
    offer.ingredients = data["ingredients"]
    offer.allergens = data["allergens"]

    # Só venda única pode estar "vendida" e só ela não pode estar "esgotada":
    # ao mudar de tipo, o anúncio volta a ficar ativo.
    if (offer.kind != Offer.Kind.ONE_OFF and offer.status == Offer.Status.SOLD) or (
        offer.kind == Offer.Kind.ONE_OFF and offer.status == Offer.Status.SOLD_OUT
    ):
        offer.status = Offer.Status.ACTIVE
        offer.status_changed_at = now

    # A confirmação de hoje vale para o tipo em que foi feita: trocar de tipo a
    # desfaz (senão a do dia vencida voltaria como recorrente até 23h59).
    if offer.kind != previous_kind:
        offer.daily_confirmed_on = None

    if offer.kind == Offer.Kind.DAILY:
        offer.closing_time = data["closing_time"]
        # Anúncio oculto não pode ser confirmado: a caixa é ignorada (o form também a
        # zera) e a confirmação que já existe fica como está.
        if offer.hidden_at is None:
            if not data["confirm_today"]:
                offer.daily_confirmed_on = None
            elif not is_available_today(offer.daily_confirmed_on, offer.closing_time, now, tz):
                # O formulário já recusou o que `confirmation_refusal` recusa; a regra é a
                # mesma do botão.
                apply_action(offer, "confirm_today", now, tz)
    else:
        offer.closing_time = None
        if offer.kind == Offer.Kind.ONE_OFF:
            offer.daily_confirmed_on = None
            # Criar ou editar venda única conta como reconfirmação (D10, CA10).
            offer.last_confirmed_at = now


def _save_variants(offer: Offer, variants: list[tuple[str, int]]) -> None:
    offer.variants.all().delete()
    OfferVariant.objects.bulk_create(
        OfferVariant(offer=offer, name=name, price_cents=cents, position=position)
        for position, (name, cents) in enumerate(variants)
    )


class OfferLimitReached(Exception):
    """O vendedor chegou ao teto de anúncios (S1). `message` vai para o formulário."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _check_offer_limits(seller: Seller, trusted: bool) -> None:
    """Levanta `OfferLimitReached` se o vendedor não pode criar mais um anúncio."""
    offers = Offer.objects.filter(seller=seller)
    if offers.count() >= MAX_OFFERS_PER_SELLER:
        raise OfferLimitReached(texts.OFFER_LIMIT_REACHED.format(max=MAX_OFFERS_PER_SELLER))
    if not trusted and (
        offers.filter(approval=Offer.Approval.PENDING).count() >= MAX_PENDING_UNTRUSTED
    ):
        raise OfferLimitReached(texts.PENDING_LIMIT_REACHED.format(max=MAX_PENDING_UNTRUSTED))


def create_offer(seller: Seller, data: dict, files: list, now: datetime, tz: ZoneInfo) -> Offer:
    """Novo anúncio. Vendedor ainda não confiável começa "Aguardando aprovação" (CA12, D12).

    Levanta `OfferLimitReached` (nada é gravado) se passar do teto de anúncios (S1).
    A linha do vendedor fica travada para dois envios ao mesmo tempo não furarem o teto.
    """
    with transaction.atomic():
        trusted = Seller.objects.select_for_update().get(pk=seller.pk).is_trusted
        _check_offer_limits(seller, trusted)
        offer = Offer(
            seller=seller,
            status=Offer.Status.ACTIVE,
            status_changed_at=now,
            last_confirmed_at=now,
            approval=Offer.Approval.APPROVED if trusted else Offer.Approval.PENDING,
            approved_at=now if trusted else None,
        )
        _apply_fields(offer, data, now, tz)
        offer.save()
        _save_variants(offer, data["variants"])
        if files:
            save_offer_photos(offer, files, [])
    return offer


def update_offer(offer: Offer, data: dict, files: list, now: datetime, tz: ZoneInfo) -> Offer:
    """Grava a edição. Aprovação e ocultação não mudam (D12)."""
    with transaction.atomic():
        locked = Offer.objects.select_for_update().get(pk=offer.pk, seller_id=offer.seller_id)
        _apply_fields(locked, data, now, tz)
        locked.save()
        _save_variants(locked, data["variants"])
        remove_ids = data.get("remove_photos") or []
        if files or remove_ids:
            save_offer_photos(locked, files, remove_ids)
    return locked


def created_message(offer: Offer) -> str:
    if offer.approval != Offer.Approval.APPROVED:
        return texts.OFFER_CREATED_PENDING
    if not has_public_contact(offer.seller, demo_enabled=settings.DEMO_DATA):
        return texts.OFFER_CREATED_NO_CONTACT
    return texts.OFFER_CREATED


# Limite de fotos -------------------------------------------------------------------


def photos_limit(seller: Seller) -> int:
    """Arquivos por hora: menos para quem ainda não é confiável (S1)."""
    return PHOTOS_LIMIT if seller.is_trusted else PHOTOS_LIMIT_UNTRUSTED


def photos_blocked(request: HttpRequest, count: int, limit: int = PHOTOS_LIMIT) -> bool:
    """True se enviar mais `count` arquivos passaria de `limit` por hora para este usuário."""
    if count <= 0:
        return False
    threshold = max(1, limit - count + 1)
    return ratelimit.is_blocked(
        PHOTOS_SCOPE, ratelimit.user_key(request), threshold, PHOTOS_WINDOW_S
    )


def register_photos(request: HttpRequest, count: int) -> None:
    """Conta os arquivos recebidos (antes de decodificar: decodificar é o que custa)."""
    if count > 0:
        ratelimit.register(PHOTOS_SCOPE, ratelimit.user_key(request), PHOTOS_WINDOW_S, amount=count)


# Perfil ---------------------------------------------------------------------------


def update_profile(seller: Seller, data: dict, now: datetime) -> str:
    """Grava o perfil e devolve a mensagem. Revogar tira o contato da vitrine na hora (CA6).

    Mudar o nome gera um link público novo (S9): o antigo, com o nome velho, deixa de
    valer e a mensagem avisa.
    """
    was_public = seller.whatsapp_public
    old_slug = seller.slug
    if data["display_name"] != seller.display_name:
        seller.slug = unique_slug(
            Seller, data["display_name"], fallback="vendedor", exclude_pk=seller.pk
        )
    seller.display_name = data["display_name"]
    seller.bio = data["bio"]
    seller.service_area = data["service_area"]
    seller.hours = data["hours"]
    seller.whatsapp_number = data["whatsapp"]
    seller.whatsapp_public = data["whatsapp_public"]
    fields = [
        "display_name",
        "slug",
        "bio",
        "service_area",
        "hours",
        "whatsapp_number",
        "whatsapp_public",
    ]
    if seller.whatsapp_public != was_public:
        seller.whatsapp_public_changed_at = now
        fields.append("whatsapp_public_changed_at")
    seller.save(update_fields=fields)
    if was_public and not seller.whatsapp_public:
        message = texts.PROFILE_CONTACT_REVOKED
    elif seller.whatsapp_public and not was_public:
        message = texts.PROFILE_CONTACT_GRANTED
    else:
        message = texts.PROFILE_SAVED
    if seller.slug != old_slug:
        message = f"{message} {texts.PROFILE_LINK_CHANGED}"
    return message
