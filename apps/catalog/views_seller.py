"""Área do vendedor: painel, formulário de anúncio, ações de um clique e perfil.

Toda view exige login e perfil de vendedor (`seller_required` põe o perfil em
`request.seller`). Anúncio sempre via `services_seller.get_own_offer` (CA11):
o de outro vendedor dá 404, em GET e em POST. Mutação só por POST com CSRF.
As páginas têm dado pessoal (o número no perfil), então não vão para cache.
"""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalog import services_seller as services
from apps.catalog.domain.actions import ACTIONS, ActionNotAllowed
from apps.catalog.forms_seller import OfferForm, ProfileForm
from apps.core import clock
from apps.core.auth import seller_required
from texts import seller as texts


def _dashboard_anchor(pk: int) -> str:
    return f"{reverse('seller:dashboard')}#anuncio-{pk}"


@never_cache
@require_http_methods(["GET", "HEAD"])
@seller_required
def dashboard(request: HttpRequest) -> HttpResponse:
    seller = request.seller
    items = services.dashboard_items(
        seller, clock.now(), clock.community_tz(), settings.RECONFIRM_DAYS
    )
    context = {
        "items": items,
        "has_pending": services.has_pending(items),
        "contact_public": services.contact_is_public(seller),
        "texts": texts,
    }
    return render(request, "seller/dashboard.html", context)


def _offer_form_view(request: HttpRequest, offer=None) -> HttpResponse:
    """GET mostra o formulário; POST valida e grava. Erro reexibe tudo (CA8)."""
    now, tz = clock.now(), clock.community_tz()
    status = 200
    if request.method == "POST":
        files = [f for f in request.FILES.getlist("photos") if f]
        blocked = services.photos_blocked(
            request, len(files), services.photos_limit(request.seller)
        )
        if files and not blocked:
            services.register_photos(request, len(files))
        form = OfferForm(
            request.POST, request.FILES, offer=offer, now=now, tz=tz, photos_blocked=blocked
        )
        if form.is_valid():
            data = form.cleaned_data
            try:
                if offer is None:
                    saved = services.create_offer(request.seller, data, data["photos"], now, tz)
                    message = services.created_message(saved)
                else:
                    saved = services.update_offer(offer, data, data["photos"], now, tz)
                    message = texts.OFFER_SAVED
            except ValidationError as exc:
                # Corrida rara: outro envio mudou as fotos entre a validação e a gravação.
                # A transação foi desfeita; o erro volta junto do campo de fotos.
                form.add_error("photos", exc)
            except services.OfferLimitReached as exc:
                form.add_error(None, exc.message)
            except ActionNotAllowed:
                # Defesa: o formulário já aplica a mesma regra de confirmação com o mesmo
                # `now`. Se ela recusar aqui, nada foi gravado; o formulário volta com um
                # aviso, nunca 500.
                form.add_error(None, texts.ACTION_FAILED)
            else:
                messages.success(request, message)
                return redirect(_dashboard_anchor(saved.pk))
        if blocked:
            status = 429
    else:
        form = OfferForm(offer=offer, now=now, tz=tz)
    context = {
        "form": form,
        "offer": offer,
        "page_title": texts.OFFER_NEW_TITLE if offer is None else texts.OFFER_EDIT_TITLE,
        "action_url": reverse("seller:offer_create")
        if offer is None
        else reverse("seller:offer_edit", args=[offer.pk]),
        "contact_public": services.contact_is_public(request.seller),
        "texts": texts,
    }
    response = render(request, "seller/offer_form.html", context, status=status)
    if status == 429:
        response["Retry-After"] = str(services.PHOTOS_WINDOW_S)
    return response


@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
@seller_required
def offer_create(request: HttpRequest) -> HttpResponse:
    return _offer_form_view(request)


@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
@seller_required
def offer_edit(request: HttpRequest, pk: int) -> HttpResponse:
    offer = services.get_own_offer(request, pk)
    return _offer_form_view(request, offer)


@require_POST
@seller_required
def offer_action(request: HttpRequest, pk: int) -> HttpResponse:
    action = request.POST.get("action", "")
    if action not in ACTIONS:
        # Confere o dono antes de responder, para não revelar se o anúncio existe.
        services.get_own_offer(request, pk)
        messages.error(request, texts.ACTION_NOT_ALLOWED)
        return redirect(_dashboard_anchor(pk))
    try:
        offer = services.run_action(
            request, pk, action, clock.now(), clock.community_tz(), settings.RECONFIRM_DAYS
        )
    except ActionNotAllowed as exc:
        messages.error(request, services.action_error_message(exc))
    else:
        messages.success(request, services.action_message(offer, action))
    return redirect(_dashboard_anchor(pk))


@never_cache
@sensitive_post_parameters("whatsapp")
@require_http_methods(["GET", "HEAD", "POST"])
@seller_required
def profile(request: HttpRequest) -> HttpResponse:
    seller = request.seller
    if request.method == "POST":
        form = ProfileForm(request.POST, seller=seller)
        if form.is_valid():
            messages.success(
                request, services.update_profile(seller, form.cleaned_data, clock.now())
            )
            return redirect("seller:profile")
    else:
        form = ProfileForm(seller=seller)
    context = {
        "form": form,
        "seller": seller,
        "contact_public": services.contact_is_public(seller),
        "public_url": request.build_absolute_uri(
            reverse("catalog:seller_detail", args=[seller.slug])
        ),
    }
    return render(request, "seller/profile.html", context)
