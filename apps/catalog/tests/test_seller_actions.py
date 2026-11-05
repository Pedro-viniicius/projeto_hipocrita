"""Painel "Meus anúncios" e ações de um clique (CA7, CA10)."""

from datetime import time, timedelta

import pytest
import time_machine
from django.contrib.messages import get_messages
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Offer
from apps.core.testing import assert_accessible_page, assert_phone_absent, parse_html
from conftest import DEFAULT_WHATSAPP
from texts import seller as texts
from texts import states as state_texts

pytestmark = pytest.mark.django_db

DASHBOARD = "/meus-anuncios/"
NOW = "2026-11-05 10:00:00-03:00"


def action_url(offer) -> str:
    return f"/meus-anuncios/{offer.pk}/acao/"


def shown_messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def article(client, offer):
    return parse_html(client.get(DASHBOARD)).find("article", id=f"anuncio-{offer.pk}")


def buttons(el) -> dict[str, str]:
    """value → texto de cada botão de ação dentro do elemento."""
    return {b.get("value"): b.text for b in el.find_all("button", name="action")}


# Painel ----------------------------------------------------------------------


def test_dashboard_is_accessible_and_lists_only_own_offers(seller_client, make_offer):
    mine = make_offer(seller_client.seller, title="Meu bolo")
    other = make_offer(title="Bolo de outra pessoa")
    response = seller_client.get(DASHBOARD)
    assert response.status_code == 200
    assert_accessible_page(response)
    html = response.content.decode()
    assert "Meu bolo" in html
    assert "Bolo de outra pessoa" not in html
    doc = parse_html(response)
    assert doc.find("article", id=f"anuncio-{mine.pk}") is not None
    assert doc.find("article", id=f"anuncio-{other.pk}") is None
    assert doc.find("a", href="/meus-anuncios/novo/") is not None
    assert "no-cache" in response["Cache-Control"]
    assert_phone_absent(response, DEFAULT_WHATSAPP)


def test_empty_dashboard(seller_client):
    doc = parse_html(seller_client.get(DASHBOARD))
    assert doc.find("section", class_="vazio") is not None
    assert "Você ainda não tem anúncios" in doc.text
    # O botão "Adicionar anúncio" aparece uma vez só.
    assert len(doc.find_all("a", href="/meus-anuncios/novo/")) == 1


def test_dashboard_warns_when_contact_is_not_public(make_seller):
    seller = make_seller(whatsapp_public=False)
    client = Client()
    client.force_login(seller.user)
    doc = parse_html(client.get(DASHBOARD))
    notice = doc.find("div", class_="aviso--warning")
    assert notice is not None
    assert texts.CONTACT_NOTICE_LINK in notice.text
    assert notice.find("a", href="/perfil/") is not None


def test_dashboard_has_no_contact_warning_when_public(seller_client):
    doc = parse_html(seller_client.get(DASHBOARD))
    assert doc.find("div", class_="aviso--warning") is None
    assert texts.PENDING_NOTICE not in doc.text


@time_machine.travel(NOW, tick=False)
def test_dashboard_shows_kind_state_price_and_actions(seller_client, make_offer):
    offer = make_offer(seller_client.seller, kind="recurring", variants=[("Grande", 1500)])
    item = article(seller_client, offer)
    assert state_texts.LABEL_ON_ORDER in item.text
    assert texts.KIND_LABELS["recurring"] in item.text
    assert "A partir de R$ 10,00" in item.text
    actions = buttons(item)
    # D7: recorrente também pode confirmar o dia; o botão vem fora do menu.
    assert actions["confirm_today"] == texts.ACTION_LABELS["confirm_today"]
    primary = item.find("button", class_="botao--confirmar")
    assert primary.get("value") == "confirm_today"
    menu = item.find("details", class_="menu-acoes")
    assert set(buttons(menu)) == {"sold_out", "pause"}
    assert item.find("a", href=f"/meus-anuncios/{offer.pk}/editar/") is not None


def test_hidden_offer_shows_badge_and_no_actions(seller_client, make_offer):
    offer = make_offer(seller_client.seller, hidden_at=timezone.now(), hidden_reason="x")
    item = article(seller_client, offer)
    assert state_texts.LABEL_HIDDEN in item.text
    assert buttons(item) == {}


# Ações (CA7) -------------------------------------------------------------------

CASES = [
    # (ação, campos iniciais, status esperado, mensagem)
    ("pause", {}, "paused", "pause"),
    ("resume", {"status": "paused"}, "active", "resume"),
    ("sold_out", {}, "sold_out", "sold_out"),
    ("restock", {"status": "sold_out"}, "active", "restock"),
    ("sold", {"kind": "one_off"}, "sold", "sold"),
    ("unsold", {"kind": "one_off", "status": "sold"}, "active", "unsold"),
]


@pytest.mark.parametrize(("action", "fields", "status", "message"), CASES)
def test_one_click_action_changes_state_and_confirms(
    seller_client, make_offer, action, fields, status, message
):
    offer = make_offer(seller_client.seller, title="Bolo de pote", **fields)
    response = seller_client.post(action_url(offer), {"action": action})
    assert response.status_code == 302
    assert response["Location"] == f"/meus-anuncios/#anuncio-{offer.pk}"
    assert shown_messages(response) == [texts.ACTION_DONE[message].format(titulo="Bolo de pote")]
    offer.refresh_from_db()
    assert offer.status == status


def test_confirmation_message_is_visible_after_redirect(seller_client, make_offer):
    offer = make_offer(seller_client.seller, title="Brownie")
    response = seller_client.post(action_url(offer), {"action": "pause"}, follow=True)
    doc = parse_html(response)
    notice = doc.find("div", class_="aviso--success")
    assert notice is not None
    assert notice.get("role") == "status"
    assert notice.text == "“Brownie” pausado. Ele saiu da vitrine."
    assert state_texts.LABEL_PAUSED in doc.find("article", id=f"anuncio-{offer.pk}").text


@time_machine.travel(NOW, tick=False)
def test_confirm_today_on_daily_offer(seller_client, make_offer, tz):
    offer = make_offer(seller_client.seller, kind="daily", title="Pão de queijo")
    response = seller_client.post(action_url(offer), {"action": "confirm_today"})
    assert shown_messages(response) == ["Pronto: “Pão de queijo” confirmado como disponível hoje."]
    offer.refresh_from_db()
    assert offer.daily_confirmed_on == timezone.now().astimezone(tz).date()
    item = article(seller_client, offer)
    assert state_texts.LABEL_AVAILABLE_TODAY in item.text
    assert "Confirmado até 23h59" in item.text
    assert "confirm_today" not in buttons(item)  # já confirmado


@time_machine.travel(NOW, tick=False)
def test_confirm_today_after_closing_time_is_refused(seller_client, make_offer):
    offer = make_offer(seller_client.seller, kind="daily", closing_time=time(9, 0))
    response = seller_client.post(action_url(offer), {"action": "confirm_today"})
    assert response.status_code == 302
    assert shown_messages(response) == [texts.ACTION_CLOSING_PASSED]
    offer.refresh_from_db()
    assert offer.daily_confirmed_on is None


@time_machine.travel("2026-11-05 23:59:00-03:00", tick=False)
def test_confirm_today_from_2359_is_refused_with_own_message(seller_client, make_offer):
    """R4: às 23:59 a confirmação já não teria efeito; o vendedor é avisado."""
    offer = make_offer(seller_client.seller, kind="recurring")
    response = seller_client.post(action_url(offer), {"action": "confirm_today"})
    assert response.status_code == 302
    assert shown_messages(response) == [texts.ACTION_DAY_OVER]
    offer.refresh_from_db()
    assert offer.daily_confirmed_on is None


def test_action_not_valid_for_state_changes_nothing(seller_client, make_offer):
    offer = make_offer(seller_client.seller, status=Offer.Status.PAUSED)
    before = offer.status_changed_at
    response = seller_client.post(action_url(offer), {"action": "pause"})
    assert response["Location"] == f"/meus-anuncios/#anuncio-{offer.pk}"
    assert shown_messages(response) == [texts.ACTION_NOT_ALLOWED]
    offer.refresh_from_db()
    assert offer.status == Offer.Status.PAUSED
    assert offer.status_changed_at == before


@pytest.mark.parametrize("value", ["", "apagar", "PAUSE"])
def test_unknown_action_changes_nothing(seller_client, make_offer, value):
    offer = make_offer(seller_client.seller)
    response = seller_client.post(action_url(offer), {"action": value})
    assert response.status_code == 302
    assert shown_messages(response) == [texts.ACTION_NOT_ALLOWED]
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACTIVE


def test_pending_offer_refuses_actions(make_seller, make_offer):
    seller = make_seller(trusted=False)
    offer = make_offer(seller, approval=Offer.Approval.PENDING)
    client = Client()
    client.force_login(seller.user)
    response = client.post(action_url(offer), {"action": "pause"})
    assert shown_messages(response) == [texts.ACTION_NOT_ALLOWED]
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACTIVE


def test_hidden_offer_refuses_actions(seller_client, make_offer):
    offer = make_offer(seller_client.seller, hidden_at=timezone.now())
    seller_client.post(action_url(offer), {"action": "pause"})
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACTIVE


def test_action_requires_post_and_csrf(seller_client, make_offer):
    offer = make_offer(seller_client.seller)
    assert seller_client.get(action_url(offer)).status_code == 405
    client = Client(enforce_csrf_checks=True)
    client.force_login(seller_client.user)
    assert client.post(action_url(offer), {"action": "pause"}).status_code == 403
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACTIVE


# Venda pontual vencida (CA10) -------------------------------------------------------


@time_machine.travel(NOW, tick=False)
def test_one_off_before_14_days_does_not_need_confirmation(seller_client, make_offer):
    last = timezone.now() - timedelta(days=13, hours=23)
    offer = make_offer(seller_client.seller, kind="one_off", last_confirmed_at=last)
    item = article(seller_client, offer)
    assert state_texts.LABEL_NEEDS_CONFIRMATION not in item.text
    assert "reconfirm" not in buttons(item)
    assert "Última confirmação há 13 dias" in item.text


@time_machine.travel(NOW, tick=False)
def test_one_off_after_14_days_needs_confirmation_and_reactivates_with_one_click(
    seller_client, make_offer
):
    last = timezone.now() - timedelta(days=14)
    offer = make_offer(
        seller_client.seller, kind="one_off", title="Apostila", last_confirmed_at=last
    )
    item = article(seller_client, offer)
    assert state_texts.LABEL_NEEDS_CONFIRMATION in item.text
    primary = item.find("button", class_="botao--confirmar")
    assert primary.get("value") == "reconfirm"
    assert primary.text == texts.ACTION_LABELS["reconfirm"]

    response = seller_client.post(action_url(offer), {"action": "reconfirm"})
    assert shown_messages(response) == [texts.ACTION_DONE["reconfirm"].format(titulo="Apostila")]
    offer.refresh_from_db()
    assert offer.last_confirmed_at == timezone.now()
    item = article(seller_client, offer)
    assert state_texts.LABEL_NEEDS_CONFIRMATION not in item.text
    assert "Última confirmação hoje" in item.text


@time_machine.travel(NOW, tick=False)
def test_reconfirm_is_refused_when_not_needed(seller_client, make_offer):
    last = timezone.now() - timedelta(days=2)
    offer = make_offer(seller_client.seller, kind="one_off", last_confirmed_at=last)
    response = seller_client.post(action_url(offer), {"action": "reconfirm"})
    assert shown_messages(response) == [texts.ACTION_NOT_ALLOWED]
    offer.refresh_from_db()
    assert offer.last_confirmed_at == last


@time_machine.travel(NOW, tick=False)
def test_resume_one_off_renews_confirmation(seller_client, make_offer):
    last = timezone.now() - timedelta(days=30)
    offer = make_offer(
        seller_client.seller, kind="one_off", status=Offer.Status.PAUSED, last_confirmed_at=last
    )
    seller_client.post(action_url(offer), {"action": "resume"})
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACTIVE
    assert offer.last_confirmed_at == timezone.now()
