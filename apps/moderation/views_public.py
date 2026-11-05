"""Denúncia pública, sem cadastro (CA12, CA14).

- Limite de 5 envios por hora por IP (`apps.core.ratelimit`, que guarda só o
  HMAC do IP por até 24 h). A denúncia em si não guarda IP nem identificação.
- CSRF do Django no POST.
- `details` é texto livre e pode ter dado pessoal de terceiros: nunca vai para log.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apps.catalog import selectors
from apps.catalog.domain.availability import is_page_visible
from apps.catalog.views_public import offer_unavailable
from apps.core import clock, ratelimit
from apps.moderation.forms_public import ReportForm
from texts import public as texts

REPORT_LIMIT = 5
REPORT_WINDOW_S = 60 * 60
SCOPE_REPORT = "report"


def _public_offer(pk: int):
    """O anúncio, se a página dele está no ar; senão `None`."""
    offer = selectors.visible_offer(pk)
    if offer is None:
        return None
    now, tz = clock.now(), clock.community_tz()
    if not is_page_visible(
        offer, now, tz, settings.RECONFIRM_DAYS, demo_enabled=settings.DEMO_DATA
    ):
        return None
    return offer


@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def create(request: HttpRequest, pk: int) -> HttpResponse:
    offer = _public_offer(pk)
    if offer is None:
        return offer_unavailable(request)

    status = 200
    rate_limited = False
    form = ReportForm()
    if request.method == "POST":
        key = ratelimit.client_key(request)
        if ratelimit.is_blocked(SCOPE_REPORT, key, REPORT_LIMIT, REPORT_WINDOW_S):
            rate_limited, status = True, 429
            form = ReportForm(request.POST)
        else:
            ratelimit.register(SCOPE_REPORT, key, REPORT_WINDOW_S)
            form = ReportForm(request.POST)
            if form.is_valid():
                form.save(offer)
                return redirect("report:done", pk=offer.pk)
    context = {
        "offer": offer,
        "form": form,
        "rate_limited": rate_limited,
        "rate_limited_text": texts.REPORT_RATE_LIMITED,
        "offer_url": reverse("catalog:offer_detail", kwargs={"pk": offer.pk}),
    }
    response = render(request, "public/report_form.html", context, status=status)
    if rate_limited:
        response["Retry-After"] = str(REPORT_WINDOW_S)
    return response


@require_safe
def done(request: HttpRequest, pk: int) -> HttpResponse:
    """Confirmação. Volta para a oferta, ou para o início se ela saiu do ar."""
    offer = _public_offer(pk)
    context = {
        "ok_text": texts.REPORT_OK,
        "back_url": (
            reverse("catalog:offer_detail", kwargs={"pk": offer.pk})
            if offer
            else reverse("catalog:home")
        ),
        "back_to_offer": offer is not None,
    }
    return render(request, "public/report_done.html", context)
