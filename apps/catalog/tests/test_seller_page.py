"""Página do vendedor (CA5, CA6)."""

import pytest
import time_machine

from apps.catalog.models import Offer
from apps.core.testing import (
    assert_accessible_page,
    assert_no_set_cookie,
    assert_phone_absent,
    assert_single_link_per_article,
    parse_html,
)
from conftest import DEFAULT_WHATSAPP

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen_clock():
    with time_machine.travel("2026-11-05 12:00:00-03:00", tick=False):
        yield


def url(seller) -> str:
    return f"/vendedor/{seller.slug}/"


def test_seller_page_shows_profile_link_and_active_offers(client, make_seller, make_offer):
    seller = make_seller(
        display_name="Doces da Ana",
        bio="Doces caseiros.",
        service_area="Bloco 3",
        hours="Seg a sex, 10h",
    )
    active = make_offer(seller=seller, title="Brownie")
    sold_out = make_offer(seller=seller, title="Torta", status=Offer.Status.SOLD_OUT)
    make_offer(seller=seller, title="Pausado", status=Offer.Status.PAUSED)
    make_offer(seller=seller, title="Pendente", approval=Offer.Approval.PENDING)
    make_offer(title="De outro vendedor")

    response = client.get(url(seller))
    assert response.status_code == 200
    assert_accessible_page(response)
    assert_phone_absent(response, DEFAULT_WHATSAPP)
    assert_no_set_cookie(response)
    assert_single_link_per_article(response)

    doc = parse_html(response)
    main = doc.find("main")
    assert main.find("h1").text == "Doces da Ana"
    assert "Doces caseiros." in main.text
    terms = dict(
        zip(
            [d.text for d in main.find_all("dt")],
            [d.text for d in main.find_all("dd")],
            strict=True,
        )
    )
    assert terms == {"Atende em": "Bloco 3", "Horários": "Seg a sex, 10h"}
    assert main.find("h2", id="vendedor-ofertas").text == "Ofertas de Doces da Ana"
    ids = {int(a.get("id").removeprefix("oferta-")) for a in main.find_all("article")}
    assert ids == {active.pk, sold_out.pk}


def test_copy_link_works_without_js(client, make_seller):
    seller = make_seller()
    doc = parse_html(client.get(url(seller)))
    field = doc.find("input", id="link-vendedor")
    assert field.has("readonly")
    assert field.get("value") == f"http://testserver/vendedor/{seller.slug}/"
    labels = [lab for lab in doc.find_all("label") if lab.get("for") == "link-vendedor"]
    assert [lab.text for lab in labels] == ["Endereço da página"]
    scripts = [s.get("src") for s in doc.find_all("script")]
    assert any(src.endswith("js/share.js") for src in scripts)
    box = doc.find("div", class_="copiar-link")
    assert box.get("data-texto-copiar") == "Copiar link"
    assert box.find("p", role="status") is not None


def test_empty_fields_are_not_shown(client, make_seller):
    seller = make_seller(bio="", service_area="", hours="")
    main = parse_html(client.get(url(seller))).find("main")
    assert main.find("dl") is None


def test_seller_without_offers_has_message(client, make_seller):
    seller = make_seller(display_name="Ana")
    main = parse_html(client.get(url(seller))).find("main")
    assert "Ana não tem ofertas ativas agora." in main.text
    assert main.find("a", href="/") is not None


def test_seller_without_public_contact_is_404(client, make_seller):
    seller = make_seller(whatsapp_public=False)
    response = client.get(url(seller))
    assert response.status_code == 404
    assert_phone_absent(response, DEFAULT_WHATSAPP)


def test_seller_with_inactive_account_is_404(client, make_seller, make_user):
    seller = make_seller(user=make_user(is_active=False))
    assert client.get(url(seller)).status_code == 404


def test_unknown_seller_is_404(client):
    assert client.get("/vendedor/nao-existe/").status_code == 404


def test_demo_seller_page_is_public(client, make_seller, make_offer, settings):
    settings.DEMO_DATA = True
    seller = make_seller(display_name="Lucas (exemplo)", is_demo=True, whatsapp_number="")
    make_offer(seller=seller, title="Aula (exemplo)")
    response = client.get(url(seller))
    assert response.status_code == 200
    assert "Aula (exemplo)" in response.content.decode()
