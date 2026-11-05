"""Denúncia pública: sem cadastro, motivo em lista, texto opcional, limite e CSRF (CA12, CA14)."""

import logging

import pytest
import time_machine
from django.test import Client

from apps.core.models import RateLimitCounter
from apps.core.testing import assert_accessible_page, assert_phone_absent, parse_html
from apps.moderation.models import Report
from conftest import DEFAULT_WHATSAPP

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def frozen_clock():
    with time_machine.travel("2026-11-05 12:00:00-03:00", tick=False):
        yield


def url(offer) -> str:
    return f"/oferta/{offer.pk}/denunciar/"


def field_error(response, name: str) -> str:
    el = parse_html(response).find(id=f"id_{name}_error")
    return el.text if el is not None else ""


def test_form_lists_reasons_and_optional_details(client, make_offer):
    offer = make_offer(title="Bolo de pote")
    response = client.get(url(offer))
    assert response.status_code == 200
    assert_accessible_page(response)
    assert_phone_absent(response, DEFAULT_WHATSAPP)
    doc = parse_html(response)
    main = doc.find("main")
    assert main.find("h1").text == "Denunciar oferta"
    assert "Bolo de pote" in main.text
    form = main.find("form", method="post")
    assert form.get("action") == url(offer)
    assert form.find("legend").text == "Qual é o problema?"
    reasons = [r.get("value") for r in form.find_all("input", type="radio")]
    assert reasons == ["misleading", "prohibited", "offensive", "unavailable", "other"]
    details = form.find("textarea", name="details")
    assert details.get("maxlength") == "500"
    label = [lab for lab in doc.find_all("label") if lab.get("for") == details.get("id")][0]
    assert label.text == "Conte mais (opcional)"
    assert "Não coloque dados pessoais seus." in form.text
    # Sem cadastro: nada de nome, e-mail ou telefone.
    names = {el.get("name") for el in form.find_all("input")} | {"details"}
    assert names <= {"csrfmiddlewaretoken", "reason", "details"}
    assert main.find("a", href=f"/oferta/{offer.pk}/").text == "Cancelar"


def test_report_is_saved_without_identification(client, make_offer):
    offer = make_offer()
    response = client.post(
        url(offer),
        {"reason": "misleading", "details": "  Pediu pix adiantado.  "},
        REMOTE_ADDR="203.0.113.9",
    )
    assert response.status_code == 302
    assert response["Location"] == f"/oferta/{offer.pk}/denunciar/enviada/"
    report = Report.objects.get()
    assert (report.offer, report.reason, report.details, report.status) == (
        offer,
        "misleading",
        "Pediu pix adiantado.",
        "open",
    )
    # Nenhuma coluna guarda IP ou quem denunciou; o limitador guarda só o HMAC.
    columns = {f.name for f in Report._meta.get_fields()}
    assert not columns & {"ip", "ip_address", "user_agent", "email", "name", "reporter"}
    assert "203.0.113.9" not in str(list(RateLimitCounter.objects.values()))


def test_details_are_optional(client, make_offer):
    offer = make_offer()
    assert client.post(url(offer), {"reason": "other"}).status_code == 302
    assert Report.objects.get().details == ""


def test_missing_reason_shows_error_and_keeps_text(client, make_offer):
    offer = make_offer()
    response = client.post(url(offer), {"details": "Texto que fica"})
    assert response.status_code == 200
    assert field_error(response, "reason") == "Escolha o motivo da denúncia."
    assert parse_html(response).find("textarea").text == "Texto que fica"
    assert not Report.objects.exists()


def test_invalid_reason_and_long_details_are_refused(client, make_offer):
    offer = make_offer()
    response = client.post(url(offer), {"reason": "spam", "details": "x" * 501})
    assert response.status_code == 200
    assert field_error(response, "reason")
    assert field_error(response, "details") == "Escreva no máximo 500 caracteres."
    assert not Report.objects.exists()


def test_done_page_links_back_to_offer(client, make_offer):
    offer = make_offer()
    response = client.get(f"/oferta/{offer.pk}/denunciar/enviada/")
    assert response.status_code == 200
    assert_accessible_page(response)
    main = parse_html(response).find("main")
    assert "Recebemos sua denúncia. Obrigado por avisar." in main.text
    assert main.find("a", href=f"/oferta/{offer.pk}/").text == "Voltar para a oferta"


def test_done_page_goes_home_when_offer_left(client, make_offer):
    offer = make_offer(status="paused")
    main = parse_html(client.get(f"/oferta/{offer.pk}/denunciar/enviada/")).find("main")
    assert main.find("a", href="/").text == "Ir para o início"


def test_unavailable_offer_cannot_be_reported(client, make_offer):
    offer = make_offer(approval="pending")
    assert client.get(url(offer)).status_code == 404
    assert client.post(url(offer), {"reason": "other"}).status_code == 404
    assert client.get("/oferta/999999/denunciar/").status_code == 404
    assert not Report.objects.exists()


def test_limit_of_5_per_hour_per_ip(client, make_offer):
    offer = make_offer()
    for _ in range(5):
        assert (
            client.post(url(offer), {"reason": "other"}, REMOTE_ADDR="198.51.100.7").status_code
            == 302
        )
    response = client.post(url(offer), {"reason": "other"}, REMOTE_ADDR="198.51.100.7")
    assert response.status_code == 429
    assert "Você enviou muitas denúncias em pouco tempo." in parse_html(response).text
    assert_accessible_page(response)
    assert Report.objects.count() == 5
    # Outro IP continua podendo denunciar.
    assert (
        client.post(url(offer), {"reason": "other"}, REMOTE_ADDR="198.51.100.8").status_code == 302
    )
    # Na hora seguinte, o limite volta.
    with time_machine.travel("2026-11-05 13:00:01-03:00", tick=False):
        assert (
            client.post(url(offer), {"reason": "other"}, REMOTE_ADDR="198.51.100.7").status_code
            == 302
        )


def test_csrf_is_required(make_offer):
    offer = make_offer()
    strict = Client(enforce_csrf_checks=True)
    assert strict.post(url(offer), {"reason": "other"}).status_code == 403
    assert not Report.objects.exists()
    page = strict.get(url(offer))
    token = parse_html(page).find("input", name="csrfmiddlewaretoken").get("value")
    assert (
        strict.post(url(offer), {"reason": "other", "csrfmiddlewaretoken": token}).status_code
        == 302
    )


def test_details_never_go_to_logs(client, make_offer, caplog):
    offer = make_offer()
    with caplog.at_level(logging.DEBUG):
        client.post(url(offer), {"reason": "other", "details": "segredo-da-denuncia"})
    assert "segredo-da-denuncia" not in caplog.text
