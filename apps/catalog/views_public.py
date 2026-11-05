"""Vitrine pública: lista, oferta, contato pelo WhatsApp e página do vendedor.

Regras que valem para todas as views daqui:
- funcionam sem JavaScript (links e formulários GET);
- não gravam cookie nem sessão (CA16); as métricas são só contagens por dia;
- o número de WhatsApp nunca vai para o HTML: aparece só no `Location` do 302
  de `offer_whatsapp` (CA6), e nunca em log;
- anúncio de demonstração só é público com `DEMO_DATA` ligado (`demo_enabled`).
"""

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.catalog import presenters, selectors
from apps.catalog.domain.availability import can_contact, is_page_visible
from apps.catalog.domain.pricing import format_brl
from apps.catalog.domain.states import PublicState
from apps.catalog.domain.whatsapp import build_message, build_whatsapp_url
from apps.catalog.models import Offer
from apps.core import clock
from apps.core.ratelimit import rate_limited
from apps.metrics import recording
from texts import public as texts

# Limite do contato pelo WhatsApp: 60 por hora por IP (o 302 entrega o número).
WHATSAPP_RATE_LIMIT = 60
WHATSAPP_RATE_WINDOW_S = 60 * 60


def _now_tz():
    return clock.now(), clock.community_tz()


def offer_unavailable(request: HttpRequest) -> HttpResponse:
    """404 da oferta que não está no ar, sem dizer o motivo (D11, spec 3.10)."""
    context = {
        "title": texts.UNAVAILABLE_TITLE,
        "message": texts.UNAVAILABLE_TEXT,
        "action_label": texts.UNAVAILABLE_ACTION,
    }
    return render(request, "errors/404.html", context, status=404)


# Página inicial -----------------------------------------------------------------


def _category_chips(categories, params: presenters.ListParams) -> list[dict]:
    chips = [
        {
            "label": texts.CATEGORY_ALL,
            "url": params.home_url(cat="", pagina=1),
            "active": not params.cat,
        }
    ]
    chips += [
        {
            "label": c.name,
            "url": params.home_url(cat=c.slug, pagina=1),
            "active": c.slug == params.cat,
        }
        for c in categories
    ]
    return chips


def _list_heading(params: presenters.ListParams) -> str:
    if params.q:
        return texts.LIST_TITLE_SEARCH.format(term=params.q)
    if params.hoje:
        return texts.LIST_TITLE_TODAY
    return texts.LIST_TITLE


def _empty_state(params: presenters.ListParams) -> dict:
    """Estado vazio da lista (spec 3.1): sem ofertas publicadas ou sem resultado."""
    clear = {"acao_url": reverse("catalog:home"), "acao_texto": texts.CLEAR_FILTERS}
    if not params.has_filters:
        return {
            "titulo": texts.EMPTY_TITLE,
            "texto": texts.EMPTY_TEXT,
            "acao_url": reverse("accounts:signup"),
            "acao_texto": texts.EMPTY_ACTION,
        }
    if params.q:
        return clear | {
            "titulo": texts.NO_RESULTS_SEARCH_TITLE.format(term=params.q),
            "texto": texts.NO_RESULTS_SEARCH_TEXT,
        }
    if params.hoje and not params.cat:
        return clear | {
            "titulo": texts.NO_RESULTS_TODAY_TITLE,
            "texto": texts.NO_RESULTS_TODAY_TEXT,
        }
    return clear | {"titulo": texts.NO_RESULTS_FILTER_TITLE, "texto": texts.NO_RESULTS_FILTER_TEXT}


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    """Lista com busca, categoria, "Disponíveis hoje", rodízio e páginas cumulativas."""
    now, tz = _now_tz()
    categories = selectors.active_categories()
    by_slug = {c.slug: c for c in categories}
    params = presenters.ListParams.from_query(request.GET, set(by_slug))

    offers = selectors.list_offers(
        selectors.public_candidates(category=by_slug.get(params.cat)),
        q=params.q,
        today_only=params.hoje,
        now=now,
        tz=tz,
        days=settings.RECONFIRM_DAYS,
    )
    shown = offers[: params.pagina * presenters.PAGE_SIZE]
    has_more = len(offers) > len(shown)

    # Só a busca pura conta: com categoria ou "hoje", o vazio pode ser do filtro (R9).
    pure_search = params.q and not params.cat and not params.hoje
    if pure_search and not offers and recording.is_countable(request):
        recording.record_search_miss(params.q, now.astimezone(tz).date())

    more_url = ""
    if has_more:
        first_new = offers[len(shown)]
        more_url = params.home_url(
            anchor=presenters.anchor_id(first_new.pk), pagina=params.pagina + 1
        )

    context = {
        "params": params,
        "page_title": _list_heading(params) if params.has_filters else texts.HOME_PAGE_TITLE,
        "heading": texts.HOME_HEADING,
        "list_heading": _list_heading(params),
        "categories": _category_chips(categories, params),
        "today_url": params.home_url(hoje=not params.hoje, pagina=1),
        "cards": presenters.build_cards(shown, now=now, tz=tz, params=params),
        "more_url": more_url,
        "more_label": texts.LIST_MORE,
        "empty": None if shown else _empty_state(params),
    }
    return render(request, "public/home.html", context)


# Página da oferta -----------------------------------------------------------------


def _food_rows(offer: Offer) -> list[dict]:
    """Porção, ingredientes e alergênicos; vazio vira "Não informado pelo vendedor"."""
    if not offer.category.is_food:
        return []
    fields = (
        (texts.FOOD_PORTION, offer.portion),
        (texts.FOOD_INGREDIENTS, offer.ingredients),
        (texts.FOOD_ALLERGENS, offer.allergens),
    )
    return [
        {"label": label, "value": value.strip(), "missing": not value.strip()}
        for label, value in fields
    ]


def _photos(offer: Offer) -> list[dict]:
    photos = []
    for n, photo in enumerate(offer.photos.all(), start=1):
        alt = (
            texts.PHOTO_ALT_FIRST.format(title=offer.title)
            if n == 1
            else texts.PHOTO_ALT_OTHER.format(n=n, title=offer.title)
        )
        photos.append(
            {"url": photo.page_image.url, "w": photo.page_width, "h": photo.page_height, "alt": alt}
        )
    return photos


@require_safe
def offer_detail(request: HttpRequest, pk: int) -> HttpResponse:
    now, tz = _now_tz()
    days, demo = settings.RECONFIRM_DAYS, settings.DEMO_DATA
    offer = selectors.visible_offer(pk)
    if offer is None or not is_page_visible(offer, now, tz, days, demo_enabled=demo):
        return offer_unavailable(request)

    if recording.is_countable(request, owner_user_id=offer.seller.user_id):
        recording.record_offer_view(offer.pk, now.astimezone(tz).date())

    params = presenters.ListParams.from_query(request.GET)
    state, state_vm = presenters.offer_state(offer, now, tz)
    price_label, price_from = presenters.price_info(offer)
    seller = offer.seller
    status_message = ""
    if state == PublicState.SOLD:
        status_message = texts.OFFER_SOLD
    elif offer.status == Offer.Status.SOLD_OUT:
        # Também sem selo (oferta do dia esgotada em outro dia): explica a falta do botão.
        status_message = texts.OFFER_SOLD_OUT

    context = {
        "offer": offer,
        "page_title": offer.title,
        "back_url": params.home_url(anchor=presenters.anchor_id(offer.pk)),
        "state": state_vm,
        "price_label": price_label,
        "price_from": price_from,
        "price_struck": state == PublicState.SOLD,
        "photos": _photos(offer),
        "food_rows": _food_rows(offer),
        "food_missing_label": texts.FOOD_NOT_INFORMED,
        "variants": [
            {"id": v.pk, "name": v.name, "price_label": format_brl(v.price_cents)}
            for v in offer.variants.all()
        ],
        "can_contact": can_contact(offer, now, tz, days, demo_enabled=demo),
        "status_message": status_message,
        "seller": seller,
        "seller_initials": presenters.initials(seller.display_name),
        "seller_url": reverse("catalog:seller_detail", kwargs={"slug": seller.slug}),
        "seller_other_label": texts.OFFER_OTHER_FROM_SELLER.format(name=seller.display_name),
    }
    return render(request, "public/offer_detail.html", context)


# Contato pelo WhatsApp ----------------------------------------------------------


def _chosen_variant(offer: Offer, raw: str | None) -> str | None:
    """Nome da variação escolhida (`?variacao=<id>`), só se for desta oferta."""
    try:
        variant_id = int(raw or "")
    except ValueError:
        return None
    for variant in offer.variants.all():
        if variant.pk == variant_id:
            return variant.name
    return None


@never_cache
@require_safe
@rate_limited("whatsapp", WHATSAPP_RATE_LIMIT, WHATSAPP_RATE_WINDOW_S, methods=("GET", "HEAD"))
def offer_whatsapp(request: HttpRequest, pk: int) -> HttpResponse:
    """Conta o clique e responde 302 para o wa.me com a mensagem pronta (CA1, CA6).

    404 se o contato não vale agora (oferta fora do ar, esgotada ou vendida).
    429 depois de 60 contatos na hora pelo mesmo IP (S8): HEAD conta no limite, porque
    devolve o mesmo 302 com o número, mas não conta na métrica (`is_countable`).
    Anúncio de demonstração nunca abre o WhatsApp: mostra uma página explicando (D23).
    """
    now, tz = _now_tz()
    offer = selectors.visible_offer(pk)
    if offer is None or not can_contact(
        offer, now, tz, settings.RECONFIRM_DAYS, demo_enabled=settings.DEMO_DATA
    ):
        return offer_unavailable(request)

    variant = _chosen_variant(offer, request.GET.get("variacao"))
    page_url = request.build_absolute_uri(reverse("catalog:offer_detail", kwargs={"pk": offer.pk}))
    message = build_message(offer.title, variant, page_url)

    if recording.is_countable(request, owner_user_id=offer.seller.user_id):
        recording.record_whatsapp_click(offer.pk, now.astimezone(tz).date())

    if offer.seller.is_demo:
        context = {"offer": offer, "message": message, "back_url": presenters.offer_url(offer.pk)}
        return render(request, "public/demo_contact.html", context)

    try:
        target = build_whatsapp_url(offer.seller.whatsapp_number, message)
    except ValueError:
        # Número salvo fora do formato: trata como contato indisponível (sem logar o número).
        return offer_unavailable(request)
    response = HttpResponseRedirect(target)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


# Página do vendedor --------------------------------------------------------------


@require_safe
def seller_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Nome, apresentação, região, horários, link copiável e ofertas no ar (CA5)."""
    seller = selectors.public_seller(slug)
    if seller is None:
        raise Http404
    now, tz = _now_tz()
    offers = selectors.list_offers(
        selectors.public_candidates(seller=seller),
        q="",
        today_only=False,
        now=now,
        tz=tz,
        days=settings.RECONFIRM_DAYS,
    )
    page_url = request.build_absolute_uri(
        reverse("catalog:seller_detail", kwargs={"slug": seller.slug})
    )
    context = {
        "seller": seller,
        "page_url": page_url,
        "cards": presenters.build_cards(offers, now=now, tz=tz),
        "offers_heading": texts.SELLER_OFFERS_TITLE.format(name=seller.display_name),
        "no_offers": texts.SELLER_NO_OFFERS.format(name=seller.display_name),
    }
    return render(request, "public/seller_detail.html", context)
