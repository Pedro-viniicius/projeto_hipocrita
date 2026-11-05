"""Checagens automáticas de acessibilidade das páginas públicas (CA3, CA20).

Cada página passa por `assert_accessible_page` (lang pt-BR, um h1, `main`,
rótulos, alt, ids únicos, nada inline, CSRF) e pelo `assert_phone_absent`.
"""

import pytest
import time_machine
from django.core.files.base import ContentFile

from apps.catalog.models import Offer, OfferPhoto
from apps.core.testing import (
    assert_accessible_page,
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


@pytest.fixture
def catalog(make_seller, make_offer):
    seller = make_seller(display_name="Doces da Ana", bio="Doces.", service_area="Bloco 3")
    offer = make_offer(
        seller=seller,
        title="Bolo de pote",
        variants=[("Ninho", 800), ("Brigadeiro", 700)],
        daily_confirmed_on=None,
    )
    OfferPhoto.objects.create(
        offer=offer,
        position=0,
        card_image=ContentFile(b"c", name="c.webp"),
        page_image=ContentFile(b"p", name="p.webp"),
        page_width=800,
        page_height=600,
    )
    make_offer(seller=seller, title="Torta", status=Offer.Status.SOLD_OUT)
    return seller, offer


def public_pages(seller, offer) -> list[str]:
    return [
        "/",
        "/?q=bolo",
        "/?q=nada-disso",
        "/?hoje=1",
        "/?cat=bebidas",
        f"/oferta/{offer.pk}/",
        f"/vendedor/{seller.slug}/",
        f"/oferta/{offer.pk}/denunciar/",
        f"/oferta/{offer.pk}/denunciar/enviada/",
        "/oferta/999999/",
    ]


def test_every_public_page_is_accessible_and_has_no_phone(client, catalog):
    seller, offer = catalog
    for path in public_pages(seller, offer):
        response = client.get(path)
        assert response.status_code in (200, 404), path
        assert_accessible_page(response)
        assert_phone_absent(response, DEFAULT_WHATSAPP)


def test_report_form_with_errors_is_accessible(client, catalog):
    _, offer = catalog
    response = client.post(f"/oferta/{offer.pk}/denunciar/", {"details": "x"})
    assert response.status_code == 200
    assert_accessible_page(response)
    doc = parse_html(response)
    assert doc.find("title").text.startswith("Erro:")
    assert doc.find(role="alert") is not None


def test_cards_are_one_link_each_with_text_state(client, catalog):
    response = client.get("/")
    assert_single_link_per_article(response)
    doc = parse_html(response)
    for article in doc.find_all("article"):
        seal = article.find("span", class_="selo")
        if seal is not None:
            assert seal.text  # estado com texto, nunca só cor
            assert seal.find("svg").get("aria-hidden") == "true"
        img = article.find("img")
        if img is not None:
            assert img.get("alt") == ""  # o título já está ao lado


def test_variant_radios_have_labels_inside_fieldset(client, catalog):
    _, offer = catalog
    doc = parse_html(client.get(f"/oferta/{offer.pk}/"))
    fieldset = doc.find("fieldset")
    assert fieldset.find("legend").text
    for radio in fieldset.find_all("input", type="radio"):
        labels = [lab for lab in doc.find_all("label") if lab.get("for") == radio.get("id")]
        assert len(labels) == 1 and labels[0].text


def test_headings_do_not_skip_levels(client, catalog):
    seller, offer = catalog
    for path in ["/", f"/oferta/{offer.pk}/", f"/vendedor/{seller.slug}/"]:
        doc = parse_html(client.get(path))
        levels = [int(el.tag[1]) for el in doc.iter() if el.tag in {"h1", "h2", "h3", "h4"}]
        assert levels[0] == 1, path
        for before, after in zip(levels, levels[1:], strict=False):
            assert after <= before + 1, (path, levels)


def test_filters_use_links_with_aria_current(client, catalog):
    doc = parse_html(client.get("/?cat=comidas-e-doces"))
    nav = doc.find("nav", aria_label="Categorias")
    current = [a for a in nav.find_all("a") if a.get("aria-current") == "true"]
    assert [a.text for a in current] == ["Comidas e doces"]
