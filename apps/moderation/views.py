"""Área de administração própria (`/admin/`).

Toda view exige `is_staff` (`staff_required`: anônimo vai para `/entrar/`,
logado sem permissão recebe 403) antes de qualquer outra checagem. Toda
mutação é POST e passa pelo CSRF do middleware. As regras ficam em
`services.py`; aqui só se lê a requisição, chama o serviço e responde.
As páginas não vão para cache (`never_cache`): mostram texto de denúncia.
"""

from dataclasses import dataclass

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.catalog.domain.pricing import display_price
from apps.catalog.domain.search import MAX_QUERY_LENGTH
from apps.catalog.domain.states import SellerState, StateVM, seller_state, state_vm
from apps.catalog.models import Category, Offer
from apps.core import clock
from apps.core.auth import staff_required
from apps.moderation import services
from apps.moderation.forms import CategoryForm, HideOfferForm
from apps.moderation.models import Report
from texts import moderation as texts

NEW_CATEGORY_PREFIX = "nova"


@dataclass(frozen=True)
class OfferRow:
    """Linha de anúncio nas listas e na prévia da administração."""

    offer: Offer
    state: StateVM | None
    is_pending: bool
    is_hidden: bool
    price_cents: int
    price_from: bool
    photo_url: str


@dataclass(frozen=True)
class ReportRow:
    report: Report
    reason_label: str
    is_open: bool


def _offer_row(offer: Offer, *, with_extras: bool = False) -> OfferRow:
    """Estado como o vendedor vê (inclui oculto e aguardando aprovação), preço e miniatura.

    `with_extras` usa fotos e variações (pré-carregadas com `prefetch_related`).
    """
    state = seller_state(offer, clock.now(), clock.community_tz(), settings.RECONFIRM_DAYS)
    price_cents, price_from = offer.price_cents, False
    photo_url = ""
    if with_extras:
        variants = [variant.price_cents for variant in offer.variants.all()]
        price_cents, price_from = display_price(offer.price_cents, variants)
        photos = list(offer.photos.all())
        if photos:
            photo_url = photos[0].card_image.url
    return OfferRow(
        offer=offer,
        state=state_vm(state),
        is_pending=state == SellerState.PENDING_APPROVAL,
        is_hidden=offer.hidden_at is not None,
        price_cents=price_cents,
        price_from=price_from,
        photo_url=photo_url,
    )


def _redirect_back(request: HttpRequest, default: str) -> HttpResponse:
    """Volta para a página de origem (`next`, só dentro de `/admin/`) ou para `default`."""
    target = request.POST.get("next", "")
    if (
        target.startswith("/admin/")
        and not target.startswith("//")
        and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
    ):
        return redirect(target)
    return redirect(default)


# Aprovações e anúncios -------------------------------------------------------


@never_cache
@staff_required
@require_safe
def approvals(request: HttpRequest) -> HttpResponse:
    rows = [_offer_row(offer, with_extras=True) for offer in services.pending_offers()]
    return render(request, "moderation/approvals.html", {"rows": rows, "active_tab": "approvals"})


@never_cache
@staff_required
@require_safe
def offers(request: HttpRequest) -> HttpResponse:
    q = request.GET.get("q", "")[:MAX_QUERY_LENGTH].strip()
    rows = [_offer_row(offer) for offer in services.search_offers(q)]
    context = {
        "rows": rows,
        "q": q,
        "limit": services.OFFER_LIST_LIMIT,
        "active_tab": "offers",
    }
    return render(request, "moderation/offers.html", context)


def _render_preview(request: HttpRequest, offer: Offer, form: HideOfferForm, status: int = 200):
    offer = (
        Offer.objects.select_related("seller", "category")
        .prefetch_related("photos", "variants")
        .get(pk=offer.pk)
    )
    context = {
        "row": _offer_row(offer, with_extras=True),
        "offer": offer,
        "photos": list(offer.photos.all()),
        "variants": list(offer.variants.all()),
        "hide_form": form,
        "active_tab": "approvals" if offer.approval == Offer.Approval.PENDING else "offers",
    }
    return render(request, "moderation/offer_preview.html", context, status=status)


@never_cache
@staff_required
@require_safe
def offer_preview(request: HttpRequest, pk: int) -> HttpResponse:
    """Prévia do anúncio em qualquer estado (inclusive pendente ou oculto), só para o admin."""
    offer = get_object_or_404(Offer, pk=pk)
    return _render_preview(request, offer, HideOfferForm())


@never_cache
@staff_required
@require_POST
def offer_approve(request: HttpRequest, pk: int) -> HttpResponse:
    offer = get_object_or_404(Offer, pk=pk)
    services.approve_offer(offer.pk, by=request.user, now=clock.now())
    messages.success(request, texts.OFFER_APPROVED)
    return _redirect_back(request, reverse("moderation:approvals"))


@never_cache
@staff_required
@require_POST
def offer_hide(request: HttpRequest, pk: int) -> HttpResponse:
    offer = get_object_or_404(Offer, pk=pk)
    form = HideOfferForm(request.POST)
    if not form.is_valid():
        return _render_preview(request, offer, form, status=400)
    services.hide_offer(offer.pk, form.cleaned_data["reason"], by=request.user, now=clock.now())
    messages.success(request, texts.OFFER_HIDDEN)
    return _redirect_back(request, reverse("moderation:offers"))


@never_cache
@staff_required
@require_POST
def offer_show(request: HttpRequest, pk: int) -> HttpResponse:
    offer = get_object_or_404(Offer, pk=pk)
    services.show_offer(offer.pk, by=request.user)
    messages.success(request, texts.OFFER_SHOWN)
    return _redirect_back(request, reverse("moderation:offers"))


# Denúncias -------------------------------------------------------------------


@never_cache
@staff_required
@require_safe
def reports(request: HttpRequest) -> HttpResponse:
    rows = [
        ReportRow(
            report=report,
            reason_label=texts.REPORT_REASONS.get(report.reason, report.reason),
            is_open=report.status == Report.Status.OPEN,
        )
        for report in services.reports_for_admin()
    ]
    context = {
        "rows": rows,
        "has_open": any(row.is_open for row in rows),
        "active_tab": "reports",
    }
    return render(request, "moderation/reports.html", context)


@never_cache
@staff_required
@require_POST
def report_resolve(request: HttpRequest, pk: int) -> HttpResponse:
    """Marca como tratada; com `hide=1`, também oculta o anúncio denunciado."""
    report = get_object_or_404(Report, pk=pk)
    hide = request.POST.get("hide") == "1"
    services.resolve_report(report.pk, by=request.user, now=clock.now(), hide=hide)
    messages.success(request, texts.REPORT_RESOLVED_AND_HIDDEN if hide else texts.REPORT_RESOLVED)
    return _redirect_back(request, reverse("moderation:reports"))


# Categorias ------------------------------------------------------------------


def _category_prefix(category: Category) -> str:
    return f"cat-{category.pk}"


def _render_categories(
    request: HttpRequest,
    *,
    new_form: CategoryForm | None = None,
    bound: CategoryForm | None = None,
    status: int = 200,
) -> HttpResponse:
    rows = []
    for category in Category.objects.order_by("position", "name"):
        if bound is not None and bound.instance.pk == category.pk:
            form = bound
        else:
            form = CategoryForm(instance=category, prefix=_category_prefix(category))
        rows.append((category, form))
    context = {
        "rows": rows,
        "new_form": new_form or CategoryForm(prefix=NEW_CATEGORY_PREFIX),
        "invalid_form": new_form if new_form is not None and new_form.errors else bound,
        "active_tab": "categories",
    }
    return render(request, "moderation/categories.html", context, status=status)


@never_cache
@staff_required
@require_http_methods(["GET", "HEAD", "POST"])
def categories(request: HttpRequest) -> HttpResponse:
    """GET lista as categorias; POST cria uma nova (vai para o fim se a posição ficar vazia)."""
    if request.method != "POST":
        return _render_categories(request)
    form = CategoryForm(request.POST, prefix=NEW_CATEGORY_PREFIX)
    if form.is_valid():
        try:
            services.create_category(
                name=form.cleaned_data["name"],
                position=form.cleaned_data["position"],
                is_food=form.cleaned_data["is_food"],
                by=request.user,
            )
        except IntegrityError:
            # Outra aba criou o mesmo nome entre a validação e a gravação.
            form.add_error("name", texts.CATEGORY_NAME_TAKEN)
        else:
            messages.success(request, texts.CATEGORY_CREATED)
            return redirect("moderation:categories")
    return _render_categories(request, new_form=form, status=400)


@never_cache
@staff_required
@require_POST
def category_update(request: HttpRequest, pk: int) -> HttpResponse:
    """`action=save` renomeia, reordena e marca alimento; `hide`/`show` só mudam a visibilidade.

    Não existe excluir: qualquer outra ação responde 400 sem mudar nada.
    """
    category = get_object_or_404(Category, pk=pk)
    action = request.POST.get("action", "save")
    if action in {"hide", "show"}:
        active = action == "show"
        services.set_category_active(category, active, by=request.user)
        messages.success(request, texts.CATEGORY_SHOWN if active else texts.CATEGORY_HIDDEN)
        return redirect("moderation:categories")
    if action != "save":
        return HttpResponseBadRequest()
    form = CategoryForm(request.POST, instance=category, prefix=_category_prefix(category))
    if form.is_valid():
        try:
            services.update_category(
                category,
                name=form.cleaned_data["name"],
                position=form.cleaned_data["position"],
                is_food=form.cleaned_data["is_food"],
                by=request.user,
            )
        except IntegrityError:
            form.add_error("name", texts.CATEGORY_NAME_TAKEN)
        else:
            messages.success(request, texts.SAVED)
            return redirect("moderation:categories")
    return _render_categories(request, bound=form, status=400)
