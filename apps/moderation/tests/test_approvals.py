"""Aprovação, prévia, lista, ocultar e mostrar anúncios pela administração (CA12)."""

from datetime import timedelta

import pytest
import time_machine
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from apps.catalog.domain.availability import is_page_visible
from apps.catalog.models import Offer, OfferPhoto, Seller
from apps.core import clock
from apps.core.testing import assert_accessible_page, assert_phone_absent, parse_html
from texts import moderation as texts

NOW = "2026-11-05 10:00:00-03:00"
PHONE = "5535998887766"


@pytest.fixture
def new_seller(make_seller):
    """Vendedor novo (ainda não confiável), com WhatsApp autorizado."""
    return make_seller(trusted=False, whatsapp_number=PHONE, display_name="Doces da Ana")


@pytest.fixture
def pending(make_offer, new_seller):
    return make_offer(
        new_seller,
        title="Brigadeiro gourmet",
        approval=Offer.Approval.PENDING,
        description="Feito em casa.",
        variants=[("Caixa com 4", 1200), ("Caixa com 8", 2200)],
    )


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def _row_ids(response, prefix: str = "anuncio-") -> list[int]:
    doc = parse_html(response)
    return [
        int(tr.get("id").removeprefix(prefix))
        for tr in doc.find_all("tr")
        if (tr.get("id") or "").startswith(prefix)
    ]


# Fila de aprovação -----------------------------------------------------------


def test_queue_lists_pending_oldest_first(staff_client, make_offer, make_seller):
    seller = make_seller(trusted=False)
    newer = make_offer(seller, approval=Offer.Approval.PENDING)
    older = make_offer(seller, approval=Offer.Approval.PENDING)
    Offer.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=2))
    make_offer(seller)  # aprovado: fora da fila
    hidden = make_offer(seller, approval=Offer.Approval.PENDING, hidden_at=timezone.now())

    response = staff_client.get(reverse("moderation:approvals"))

    assert response.status_code == 200
    assert _row_ids(response) == [older.pk, newer.pk]
    assert hidden.pk not in _row_ids(response)


def test_queue_shows_details_and_preview_link(staff_client, pending):
    response = staff_client.get(reverse("moderation:approvals"))
    html = response.content.decode()

    assert "Brigadeiro gourmet" in html
    assert "Doces da Ana" in html
    assert "Comidas e doces" in html
    assert "A partir de R$ 10,00" in html  # base R$ 10,00 + variações
    assert reverse("moderation:offer_preview", args=[pending.pk]) in html
    assert "Ver como visitante" in html
    assert_phone_absent(response, PHONE)
    assert_accessible_page(response)


def test_queue_empty_state(staff_client, make_offer):
    make_offer()
    response = staff_client.get(reverse("moderation:approvals"))
    assert "Nada esperando aprovação." in response.content.decode()


# Aprovar ---------------------------------------------------------------------


def test_approve_approves_offer_and_trusts_seller(staff_client, pending, new_seller):
    with time_machine.travel(NOW, tick=False):
        response = staff_client.post(reverse("moderation:offer_approve", args=[pending.pk]))
        expected = clock.now()

    assert response.status_code == 302
    assert response["Location"] == reverse("moderation:approvals")
    pending.refresh_from_db()
    assert pending.approval == Offer.Approval.APPROVED
    assert pending.approved_at == expected
    assert Seller.objects.get(pk=new_seller.pk).is_trusted is True
    assert texts.OFFER_APPROVED in _messages(response)

    queue = staff_client.get(reverse("moderation:approvals"))
    assert pending.pk not in _row_ids(queue)


def test_approved_offer_becomes_publicly_visible(staff_client, pending):
    tz = clock.community_tz()
    assert not is_page_visible(pending, clock.now(), tz, settings.RECONFIRM_DAYS)
    staff_client.post(reverse("moderation:offer_approve", args=[pending.pk]))
    pending.refresh_from_db()
    assert is_page_visible(pending, clock.now(), tz, settings.RECONFIRM_DAYS)


def test_approve_only_touches_that_offer(staff_client, pending, make_offer, new_seller):
    """Outro anúncio pendente do mesmo vendedor continua na fila para análise."""
    other = make_offer(new_seller, approval=Offer.Approval.PENDING)
    staff_client.post(reverse("moderation:offer_approve", args=[pending.pk]))
    other.refresh_from_db()
    assert other.approval == Offer.Approval.PENDING


def test_approve_twice_keeps_first_approval_time(staff_client, pending):
    with time_machine.travel(NOW, tick=False):
        staff_client.post(reverse("moderation:offer_approve", args=[pending.pk]))
        first = clock.now()
    with time_machine.travel("2026-11-06 10:00:00-03:00", tick=False):
        staff_client.post(reverse("moderation:offer_approve", args=[pending.pk]))
    pending.refresh_from_db()
    assert pending.approved_at == first


@pytest.mark.parametrize(
    "next_url",
    ["https://exemplo.invalid/admin/", "//exemplo.invalid/admin/", "/meus-anuncios/", ""],
)
def test_redirect_ignores_next_outside_admin(staff_client, pending, next_url):
    response = staff_client.post(
        reverse("moderation:offer_approve", args=[pending.pk]), {"next": next_url}
    )
    assert response["Location"] == reverse("moderation:approvals")


def test_redirect_honors_next_inside_admin(staff_client, pending):
    target = reverse("moderation:offers") + "?q=brigadeiro"
    response = staff_client.post(
        reverse("moderation:offer_approve", args=[pending.pk]), {"next": target}
    )
    assert response["Location"] == target


# Prévia ----------------------------------------------------------------------


def test_preview_shows_pending_offer_to_staff(staff_client, pending):
    photo = OfferPhoto(offer=pending, position=0, page_width=1280, page_height=960)
    photo.card_image.save("x.webp", ContentFile(b"card"), save=False)
    photo.page_image.save("x.webp", ContentFile(b"page"), save=False)
    photo.save()

    response = staff_client.get(reverse("moderation:offer_preview", args=[pending.pk]))

    assert response.status_code == 200
    html = response.content.decode()
    doc = parse_html(response)
    assert doc.find("h1").text == "Brigadeiro gourmet"
    assert "Aguardando aprovação" in html
    assert "Feito em casa." in html
    assert "Caixa com 4" in html and "R$ 22,00" in html
    assert "Sobre este alimento" in html and "Não informado pelo vendedor" in html
    img = doc.find("img", src=photo.page_image.url)
    assert img is not None and img.get("alt") == "Brigadeiro gourmet"
    assert doc.find("form", action=reverse("moderation:offer_approve", args=[pending.pk]))
    assert_phone_absent(response, PHONE)
    assert_accessible_page(response)


def test_preview_without_photo_uses_placeholder(staff_client, pending):
    response = staff_client.get(reverse("moderation:offer_preview", args=[pending.pk]))
    assert parse_html(response).find("div", class_="foto--vazia") is not None


def test_preview_of_hidden_offer_offers_show_again(staff_client, make_offer):
    offer = make_offer(hidden_at=timezone.now(), hidden_reason="Foto com documento")
    response = staff_client.get(reverse("moderation:offer_preview", args=[offer.pk]))
    html = response.content.decode()
    assert "Oculto pela administração" in html
    assert "Foto com documento" in html
    doc = parse_html(response)
    assert doc.find("form", action=reverse("moderation:offer_show", args=[offer.pk]))
    assert doc.find("form", action=reverse("moderation:offer_hide", args=[offer.pk])) is None


# Ocultar e mostrar -----------------------------------------------------------


def test_hide_records_time_and_reason(staff_client, make_offer):
    offer = make_offer()
    with time_machine.travel(NOW, tick=False):
        response = staff_client.post(
            reverse("moderation:offer_hide", args=[offer.pk]), {"reason": "  Golpe  "}
        )
        expected = clock.now()

    assert response.status_code == 302
    assert response["Location"] == reverse("moderation:offers")
    offer.refresh_from_db()
    assert offer.hidden_at == expected
    assert offer.hidden_reason == "Golpe"
    assert texts.OFFER_HIDDEN in _messages(response)
    tz = clock.community_tz()
    assert not is_page_visible(offer, clock.now(), tz, settings.RECONFIRM_DAYS)


def test_hide_without_reason_is_allowed(staff_client, make_offer):
    offer = make_offer()
    staff_client.post(reverse("moderation:offer_hide", args=[offer.pk]))
    offer.refresh_from_db()
    assert offer.hidden_at is not None
    assert offer.hidden_reason == ""


def test_hide_with_reason_too_long_is_refused(staff_client, make_offer):
    offer = make_offer()
    response = staff_client.post(
        reverse("moderation:offer_hide", args=[offer.pk]), {"reason": "x" * 201}
    )
    assert response.status_code == 400
    assert texts.HIDE_REASON_TOO_LONG in response.content.decode()
    assert "x" * 201 in response.content.decode()  # o texto digitado volta no campo
    offer.refresh_from_db()
    assert offer.hidden_at is None
    assert_accessible_page(response)


def test_show_clears_hidden_fields(staff_client, make_offer):
    offer = make_offer(hidden_at=timezone.now(), hidden_reason="Teste")
    response = staff_client.post(reverse("moderation:offer_show", args=[offer.pk]))
    assert response.status_code == 302
    offer.refresh_from_db()
    assert offer.hidden_at is None
    assert offer.hidden_reason == ""
    assert texts.OFFER_SHOWN in _messages(response)
    tz = clock.community_tz()
    assert is_page_visible(offer, clock.now(), tz, settings.RECONFIRM_DAYS)


def test_hide_from_queue_removes_it_from_queue(staff_client, pending):
    staff_client.post(reverse("moderation:offer_hide", args=[pending.pk]))
    queue = staff_client.get(reverse("moderation:approvals"))
    assert pending.pk not in _row_ids(queue)
    pending.refresh_from_db()
    assert pending.approval == Offer.Approval.PENDING


# Lista e busca ---------------------------------------------------------------


def test_offer_list_shows_all_states(staff_client, make_offer, pending):
    visible = make_offer(title="Bolo de cenoura")
    hidden = make_offer(title="Rifa", hidden_at=timezone.now(), hidden_reason="Proibido")
    response = staff_client.get(reverse("moderation:offers"))
    html = response.content.decode()

    assert set(_row_ids(response)) == {visible.pk, hidden.pk, pending.pk}
    assert "Oculto pela administração" in html
    assert "Motivo: Proibido" in html
    doc = parse_html(response)
    assert doc.find("form", action=reverse("moderation:offer_show", args=[hidden.pk]))
    assert doc.find("form", action=reverse("moderation:offer_hide", args=[visible.pk]))
    assert_accessible_page(response)


def test_offer_search_by_title_or_seller_ignores_accents(staff_client, make_offer, make_seller):
    ana = make_seller(display_name="Doces da Ana")
    bia = make_seller(display_name="Bia Serviços")
    pao = make_offer(ana, title="Pão de mel")
    aula = make_offer(bia, title="Aula de cálculo")

    by_title = staff_client.get(reverse("moderation:offers"), {"q": "PAO"})
    assert _row_ids(by_title) == [pao.pk]

    by_seller = staff_client.get(reverse("moderation:offers"), {"q": "servicos"})
    assert _row_ids(by_seller) == [aula.pk]

    none = staff_client.get(reverse("moderation:offers"), {"q": "bicicleta"})
    assert _row_ids(none) == []
    assert "Nenhum anúncio encontrado." in none.content.decode()
    assert parse_html(none).find("input", name="q").get("value") == "bicicleta"
