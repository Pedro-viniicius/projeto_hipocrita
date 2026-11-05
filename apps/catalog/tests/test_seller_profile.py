"""Perfil do vendedor: dados, WhatsApp validado e autorização revogável (CA6, CA8)."""

import logging

import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.utils import timezone

from apps.catalog.domain.availability import has_public_contact, is_page_visible
from apps.catalog.models import Seller
from apps.core import clock
from apps.core.testing import assert_accessible_page, assert_phone_absent, parse_html
from texts import seller as texts

pytestmark = pytest.mark.django_db

URL = "/perfil/"


def payload(**overrides) -> dict:
    data = {
        "display_name": "Doces da Ana",
        "bio": "Cookies e brownies.",
        "service_area": "Blocos 1 a 3",
        "hours": "Seg a sex, 10h",
        "whatsapp": "(35) 98888-7777",
        "whatsapp_public": "sim",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def shown_messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def field_error(response, name: str) -> str:
    el = parse_html(response).find(id=f"id_{name}_error")
    return el.text if el is not None else ""


def login(seller) -> Client:
    client = Client()
    client.force_login(seller.user)
    return client


def test_profile_page_shows_data_links_and_status(seller_client):
    seller = seller_client.seller
    response = seller_client.get(URL)
    assert response.status_code == 200
    assert_accessible_page(response)
    assert "no-store" in response["Cache-Control"]  # tem o número: nada de cache
    doc = parse_html(response)
    assert doc.find("input", name="display_name").get("value") == seller.display_name
    # O próprio vendedor vê o número (formatado) para poder editar.
    assert doc.find("input", name="whatsapp").get("value") == "(35) 91234-5678"
    assert doc.find("input", name="whatsapp_public", value="sim").has("checked")
    assert "Contato liberado" in doc.text
    link = doc.find("input", id="perfil-link")
    assert link.has("readonly")
    assert link.get("value") == f"http://testserver/vendedor/{seller.slug}/"
    assert doc.find("a", href="/perfil/senha/").text == "Trocar senha"
    assert doc.find("a", href="/perfil/excluir-conta/") is not None
    assert seller.user.email in doc.text


def test_profile_without_authorization_shows_not_released(make_seller):
    client = login(make_seller(whatsapp_public=False))
    doc = parse_html(client.get(URL))
    assert "Contato não liberado" in doc.text
    assert doc.find("input", name="whatsapp_public", value="nao").has("checked")


def test_update_profile_saves_and_normalizes_number(seller_client):
    seller = seller_client.seller
    old_slug, name = seller.slug, seller.display_name
    response = seller_client.post(URL, payload(display_name=name))
    assert response.status_code == 302
    assert response["Location"] == URL
    assert shown_messages(response) == [texts.PROFILE_SAVED]
    seller.refresh_from_db()
    assert seller.display_name == name
    assert seller.bio == "Cookies e brownies."
    assert seller.service_area == "Blocos 1 a 3"
    assert seller.hours == "Seg a sex, 10h"
    assert seller.whatsapp_number == "5535988887777"
    assert seller.whatsapp_public is True
    assert seller.slug == old_slug  # mesmo nome: o link público não muda


def test_changing_name_changes_public_link_and_warns(seller_client, make_seller, make_offer):
    """S9: o link público acompanha o nome; o antigo deixa de valer e o perfil avisa."""
    make_seller(display_name="Doces da Ana")  # o slug "doces-da-ana" já tem dono
    seller = seller_client.seller
    old_slug = seller.slug
    make_offer(seller, title="Cookie")
    help_text = parse_html(seller_client.get(URL)).find(id="id_display_name_helptext").text
    assert "link da sua página também muda" in help_text

    response = seller_client.post(URL, payload(display_name="Doces da Ana"))
    assert shown_messages(response) == [f"{texts.PROFILE_SAVED} {texts.PROFILE_LINK_CHANGED}"]
    seller.refresh_from_db()
    assert seller.slug == "doces-da-ana-2"
    assert Client().get(f"/vendedor/{old_slug}/").status_code == 404
    assert "Cookie" in Client().get(f"/vendedor/{seller.slug}/").content.decode()
    link = parse_html(seller_client.get(URL)).find("input", id="perfil-link")
    assert link.get("value") == "http://testserver/vendedor/doces-da-ana-2/"

    # Salvar de novo com o mesmo nome não troca o link.
    response = seller_client.post(URL, payload(display_name="Doces da Ana", bio="Outra"))
    assert shown_messages(response) == [texts.PROFILE_SAVED]
    seller.refresh_from_db()
    assert seller.slug == "doces-da-ana-2"


def test_invalid_whatsapp_keeps_everything_and_changes_nothing(seller_client):
    seller = seller_client.seller
    response = seller_client.post(URL, payload(whatsapp="(35) 3333-4444", bio="Nova bio"))
    assert response.status_code == 200
    assert field_error(response, "whatsapp") == texts.WHATSAPP_INVALID
    doc = parse_html(response)
    assert doc.find("title").text.startswith("Erro:")
    assert doc.find("input", name="whatsapp").get("value") == "(35) 3333-4444"
    assert doc.find("textarea", name="bio").text == "Nova bio"
    assert_accessible_page(response)
    seller.refresh_from_db()
    assert seller.whatsapp_number == "5535912345678"
    assert seller.bio == ""


def test_required_fields(seller_client):
    response = seller_client.post(
        URL, payload(display_name="  ", whatsapp="", whatsapp_public=None)
    )
    assert field_error(response, "display_name") == texts.REQUIRED
    assert field_error(response, "whatsapp") == texts.REQUIRED
    assert field_error(response, "whatsapp_public") == texts.CHOICE_INVALID


def test_revoking_authorization_takes_contact_off_at_once(seller_client, make_offer):
    seller = seller_client.seller
    offer = make_offer(seller)
    now = clock.now()
    assert is_page_visible(offer, now, clock.community_tz(), 14)

    response = seller_client.post(
        URL, payload(display_name=seller.display_name, whatsapp_public="nao")
    )
    assert shown_messages(response) == [texts.PROFILE_CONTACT_REVOKED]
    seller.refresh_from_db()
    assert seller.whatsapp_public is False
    assert seller.whatsapp_public_changed_at is not None
    assert not has_public_contact(seller)
    offer.refresh_from_db()
    assert not is_page_visible(offer, clock.now(), clock.community_tz(), 14)

    # O painel explica por que os anúncios sumiram da vitrine.
    doc = parse_html(seller_client.get("/meus-anuncios/"))
    assert doc.find("div", class_="aviso--warning") is not None
    assert "Contato não liberado" in parse_html(seller_client.get(URL)).text


def test_granting_authorization_records_when(make_seller):
    seller = make_seller(whatsapp_public=False)
    client = login(seller)
    before = timezone.now()
    response = client.post(URL, payload(display_name=seller.display_name, whatsapp_public="sim"))
    assert shown_messages(response) == [texts.PROFILE_CONTACT_GRANTED]
    seller.refresh_from_db()
    assert seller.whatsapp_public is True
    assert seller.whatsapp_public_changed_at >= before


def test_saving_without_changing_authorization_keeps_timestamp(seller_client):
    seller = seller_client.seller
    response = seller_client.post(
        URL, payload(display_name=seller.display_name, whatsapp_public="sim")
    )
    assert shown_messages(response) == [texts.PROFILE_SAVED]
    seller.refresh_from_db()
    assert seller.whatsapp_public_changed_at is None


def test_invalid_authorization_value_is_refused(seller_client):
    response = seller_client.post(URL, payload(whatsapp_public="talvez"))
    assert field_error(response, "whatsapp_public") == texts.CHOICE_INVALID
    assert Seller.objects.get().whatsapp_public is True


def test_number_never_goes_to_dashboard_or_logs(seller_client, caplog):
    caplog.set_level(logging.DEBUG)
    seller_client.post(URL, payload(whatsapp="(35) 98888-7777", display_name=""))
    seller_client.post(URL, payload(whatsapp="(35) 98888-7777"))
    assert_phone_absent(seller_client.get("/meus-anuncios/"), "5535988887777")
    for variant in ("5535988887777", "98888-7777", "988887777"):
        assert variant not in caplog.text


def test_csrf_is_enforced_on_profile(seller_client):
    client = Client(enforce_csrf_checks=True)
    client.force_login(seller_client.user)
    assert client.post(URL, payload(whatsapp_public="nao")).status_code == 403
    seller_client.seller.refresh_from_db()
    assert seller_client.seller.whatsapp_public is True


def test_profile_requires_seller(client, staff_client):
    response = client.get(URL)
    assert response.status_code == 302
    assert response["Location"].startswith("/entrar/")
    assert staff_client.get(URL).status_code == 403
