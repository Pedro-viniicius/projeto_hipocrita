"""Contato pelo WhatsApp: 302 com mensagem, clique contado, número fora do HTML (CA1, CA6, CA16)."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import time_machine
from django.test import RequestFactory

from apps.catalog import views_public
from apps.catalog.models import Offer
from apps.core import clock, ratelimit
from apps.core.testing import (
    assert_accessible_page,
    assert_no_set_cookie,
    assert_phone_absent,
    parse_html,
)
from apps.metrics.models import DailyOfferStat
from conftest import DEFAULT_WHATSAPP

pytestmark = pytest.mark.django_db

BROWSER = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1"}


@pytest.fixture(autouse=True)
def frozen_clock():
    with time_machine.travel("2026-11-05 12:00:00-03:00", tick=False):
        yield


def url(offer) -> str:
    return f"/oferta/{offer.pk}/whatsapp/"


def message_of(response) -> str:
    location = urlsplit(response["Location"])
    return parse_qs(location.query)["text"][0]


def test_redirects_to_wa_me_with_message(client, make_offer):
    offer = make_offer(title="Bolo de pote")
    response = client.get(url(offer), headers=BROWSER)
    assert response.status_code == 302
    location = urlsplit(response["Location"])
    assert (location.scheme, location.netloc, location.path) == (
        "https",
        "wa.me",
        f"/{DEFAULT_WHATSAPP}",
    )
    lines = message_of(response).split("\n")
    assert lines[0] == "Oi! Vi “Bolo de pote” no Pão de Cada Dia. Ainda está disponível?"
    assert lines[1] == f"http://testserver/oferta/{offer.pk}/"
    assert_no_set_cookie(response)
    assert "no-cache" in response["Cache-Control"] or "no-store" in response["Cache-Control"]


def test_chosen_variant_goes_into_the_message(client, make_offer):
    offer = make_offer(title="Bolo", variants=[("Ninho", 800), ("Brigadeiro", 700)])
    variant = offer.variants.get(name="Brigadeiro")
    response = client.get(url(offer), {"variacao": variant.pk})
    assert message_of(response).startswith("Oi! Vi “Bolo”, opção “Brigadeiro” no Pão de Cada Dia.")


@pytest.mark.parametrize("raw", ["abc", "", "99999", "-1"])
def test_unknown_or_foreign_variant_is_ignored(client, make_offer, raw):
    offer = make_offer(title="Bolo", variants=[("Ninho", 800)])
    response = client.get(url(offer), {"variacao": raw})
    assert response.status_code == 302
    assert "opção" not in message_of(response)


def test_variant_from_another_offer_is_ignored(client, make_offer):
    other = make_offer(variants=[("Segredo", 100)])
    offer = make_offer(title="Bolo")
    response = client.get(url(offer), {"variacao": other.variants.get().pk})
    assert "Segredo" not in message_of(response)


def test_click_is_counted_atomically_per_day(client, make_offer):
    offer = make_offer()
    client.get(url(offer), headers=BROWSER)
    client.get(url(offer), headers=BROWSER)
    stat = DailyOfferStat.objects.get(offer=offer)
    assert (str(stat.date), stat.whatsapp_clicks, stat.views) == ("2026-11-05", 2, 0)


@pytest.mark.parametrize("agent", ["WhatsApp/2.24.1 A", "Googlebot/2.1", "", "SomePreview/1.0"])
def test_robots_and_previews_do_not_count(client, make_offer, agent):
    offer = make_offer()
    assert client.get(url(offer), headers={"user-agent": agent}).status_code == 302
    assert not DailyOfferStat.objects.exists()


def test_head_and_own_seller_do_not_count(client, make_offer):
    offer = make_offer()
    assert client.head(url(offer), headers=BROWSER).status_code == 302
    client.force_login(offer.seller.user)
    assert client.get(url(offer), headers=BROWSER).status_code == 302
    assert not DailyOfferStat.objects.exists()


@pytest.mark.parametrize(
    "fields",
    [
        {"status": Offer.Status.SOLD_OUT},
        {"status": Offer.Status.PAUSED},
        {"approval": Offer.Approval.PENDING},
    ],
)
def test_no_contact_when_offer_cannot_be_contacted(client, make_offer, fields):
    offer = make_offer(**fields)
    response = client.get(url(offer), headers=BROWSER)
    assert response.status_code == 404
    assert "Location" not in response
    assert_phone_absent(response, DEFAULT_WHATSAPP)
    assert not DailyOfferStat.objects.exists()


def test_sold_one_off_cannot_be_contacted(client, make_offer):
    offer = make_offer(
        kind=Offer.Kind.ONE_OFF, status=Offer.Status.SOLD, status_changed_at=clock.now()
    )
    assert client.get(url(offer)).status_code == 404


def test_expired_one_off_cannot_be_contacted(client, make_offer):
    offer = make_offer(kind=Offer.Kind.ONE_OFF, last_confirmed_at=clock.now() - timedelta(days=14))
    assert client.get(url(offer)).status_code == 404


def test_without_authorization_the_route_is_404_and_number_never_leaks(
    client, make_offer, make_seller
):
    """CA6: sem autorização, nenhuma página pública mostra o número e a rota dá 404."""
    seller = make_seller(whatsapp_public=False)
    offer = make_offer(seller=seller, title="Bolo")
    pages = [
        client.get("/"),
        client.get("/", {"q": "bolo"}),
        client.get(f"/oferta/{offer.pk}/"),
        client.get(url(offer)),
        client.get(f"/vendedor/{seller.slug}/"),
        client.get(f"/oferta/{offer.pk}/denunciar/"),
    ]
    for response in pages:
        assert_phone_absent(response, DEFAULT_WHATSAPP)
        assert "Location" not in response
    assert pages[3].status_code == 404


def test_revoking_authorization_stops_redirect_immediately(client, make_offer):
    offer = make_offer()
    assert client.get(url(offer)).status_code == 302
    offer.seller.whatsapp_public = False
    offer.seller.save()
    assert client.get(url(offer)).status_code == 404


def test_number_appears_only_in_location_never_in_public_html(client, make_offer):
    offer = make_offer(variants=[("Ninho", 800)])
    for path in ["/", f"/oferta/{offer.pk}/", f"/vendedor/{offer.seller.slug}/"]:
        assert_phone_absent(client.get(path), DEFAULT_WHATSAPP)
    response = client.get(url(offer))
    assert response.content == b""
    assert DEFAULT_WHATSAPP in response["Location"]


def test_demo_offer_shows_explanation_and_never_opens_whatsapp(
    client, make_offer, make_seller, settings
):
    settings.DEMO_DATA = True
    demo = make_seller(display_name="Doces (exemplo)", is_demo=True, whatsapp_number="")
    offer = make_offer(seller=demo, title="Cookie (exemplo)")
    response = client.get(url(offer), headers=BROWSER)
    assert response.status_code == 200
    assert "Location" not in response
    assert_accessible_page(response)
    assert_no_set_cookie(response)
    doc = parse_html(response)
    assert "exemplo" in doc.find("h1").text
    assert "Oi! Vi “Cookie (exemplo)”" in doc.text
    assert doc.find("main").find("a", href=f"/oferta/{offer.pk}/") is not None
    assert "wa.me" not in response.content.decode()


def test_post_is_not_allowed(client, make_offer):
    assert client.post(url(make_offer())).status_code == 405


def test_contact_is_rate_limited_per_ip(client, make_offer):
    """S8: o 302 entrega o número; 60 contatos por hora por IP, depois 429."""
    offer = make_offer()
    key = ratelimit.client_key(RequestFactory().get("/"))  # mesmo REMOTE_ADDR do Client
    window = views_public.WHATSAPP_RATE_WINDOW_S
    ratelimit.register("whatsapp", key, window, amount=views_public.WHATSAPP_RATE_LIMIT - 1)
    assert client.get(url(offer), headers=BROWSER).status_code == 302  # o 60º passa
    response = client.get(url(offer), headers=BROWSER)
    assert response.status_code == 429
    assert response["Retry-After"] == str(window)
    assert "Location" not in response
    assert_phone_absent(response, DEFAULT_WHATSAPP)
    assert parse_html(response).find("h1") is not None  # página padrão do 429
    # HEAD também é recusado: devolveria o mesmo 302 com o número.
    head = client.head(url(offer), headers=BROWSER)
    assert head.status_code == 429
    assert "Location" not in head
    # Outro IP não é afetado.
    other = client.get(url(offer), headers=BROWSER, REMOTE_ADDR="10.0.0.9")
    assert other.status_code == 302


def test_head_uses_the_contact_limit_but_not_the_click_metric(client, make_offer):
    """S8: HEAD gasta o limite, mas não é visita de gente: não entra na métrica."""
    offer = make_offer()
    key = ratelimit.client_key(RequestFactory().get("/"))
    window = views_public.WHATSAPP_RATE_WINDOW_S
    ratelimit.register("whatsapp", key, window, amount=views_public.WHATSAPP_RATE_LIMIT - 1)
    assert client.head(url(offer), headers=BROWSER).status_code == 302  # o 60º passa
    blocked = client.get(url(offer), headers=BROWSER)
    assert blocked.status_code == 429
    assert "Location" not in blocked
    assert not DailyOfferStat.objects.exists()


def test_demo_offer_contact_is_404_when_demo_data_is_off(client, make_offer, make_seller):
    """R3: com DEMO_DATA desligado, nem a página de demonstração do contato abre."""
    demo = make_seller(display_name="Doces (exemplo)", is_demo=True, whatsapp_number="")
    offer = make_offer(seller=demo, title="Cookie (exemplo)")
    assert client.get(url(offer), headers=BROWSER).status_code == 404
