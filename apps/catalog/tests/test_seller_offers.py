"""Formulário de anúncio: criar, editar, campos condicionais e 1ª aprovação (CA7, CA8, CA12)."""

from datetime import time, timedelta

import pytest
import time_machine
from django.conf import settings
from django.contrib.messages import get_messages
from django.test import Client
from django.utils import timezone

from apps.catalog import services_seller
from apps.catalog.domain.actions import ActionNotAllowed
from apps.catalog.models import Category, Offer
from apps.core.testing import assert_accessible_page, parse_html
from texts import seller as texts

pytestmark = pytest.mark.django_db

NEW_URL = "/meus-anuncios/novo/"
NOW = "2026-11-05 10:00:00-03:00"


def edit_url(offer) -> str:
    return f"/meus-anuncios/{offer.pk}/editar/"


def category(slug: str) -> Category:
    return Category.objects.get(slug=slug)


def payload(**overrides) -> dict:
    data = {
        "kind": "recurring",
        "title": "Bolo de pote",
        "category": category("comidas-e-doces").pk,
        "price": "8,50",
        "description": "Feito no dia.",
        "fulfillment": "Retirada no bloco 3",
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


# Página ----------------------------------------------------------------------


def test_new_form_is_accessible_and_has_conditional_sections(seller_client):
    response = seller_client.get(NEW_URL)
    assert response.status_code == 200
    assert_accessible_page(response)
    doc = parse_html(response)
    form = doc.find("form", class_="form-oferta")
    assert form.get("enctype") == "multipart/form-data"
    assert form.get("method") == "post"
    # Tipo: os três valores do contrato, nenhum marcado (o CSS não esconde nada).
    radios = form.find_all("input", name="kind")
    assert [r.get("value") for r in radios] == ["recurring", "daily", "one_off"]
    assert not any(r.has("checked") for r in radios)
    # Seções condicionais sempre no HTML (sem JS), com legenda e instrução.
    so_dia = form.find("fieldset", class_="so-dia")
    so_comida = form.find("fieldset", class_="so-comida")
    assert so_dia.find("legend").text == texts.DAILY_LEGEND
    assert so_dia.find("input", name="closing_time").get("type") == "time"
    assert so_dia.find("input", name="confirm_today").has("checked")  # marcada por padrão
    assert so_comida.find("input", name="portion") is not None
    assert so_comida.find("textarea", name="ingredients") is not None
    # Fotos: várias, só os tipos aceitos.
    photos = form.find("input", name="photos")
    assert photos.get("type") == "file"
    assert photos.has("multiple")
    assert photos.get("accept") == "image/jpeg,image/png,image/webp"
    # Cinco linhas de variação.
    assert len(form.find_all("input", name="variant_name_4")) == 1
    assert form.find("input", name="variant_name_5") is None
    assert form.find("input", name="price").get("inputmode") == "decimal"


def test_food_categories_carry_data_food(seller_client):
    doc = parse_html(seller_client.get(NEW_URL))
    options = {
        o.text: o for o in doc.find("select", name="category").find_all("option") if o.get("value")
    }
    assert options["Comidas e doces"].has("data-food")
    assert options["Bebidas"].has("data-food")
    assert not options["Serviços"].has("data-food")
    assert not options["Objetos e usados"].has("data-food")


def test_inactive_category_is_not_offered_on_create(seller_client):
    Category.objects.filter(slug="outros").update(is_active=False)
    doc = parse_html(seller_client.get(NEW_URL))
    labels = [o.text for o in doc.find("select", name="category").find_all("option")]
    assert "Outros" not in labels


# Criar e aprovação inicial (CA12) --------------------------------------------


def test_first_offer_of_new_seller_waits_for_approval(make_seller):
    seller = make_seller(trusted=False)
    client = login(seller)
    response = client.post(NEW_URL, payload())
    offer = Offer.objects.get()
    assert response.status_code == 302
    assert response["Location"] == f"/meus-anuncios/#anuncio-{offer.pk}"
    assert shown_messages(response) == [texts.OFFER_CREATED_PENDING]
    assert offer.seller == seller
    assert offer.approval == Offer.Approval.PENDING
    assert offer.approved_at is None
    assert offer.status == Offer.Status.ACTIVE
    assert offer.price_cents == 850
    assert offer.title == "Bolo de pote"

    page = client.get("/meus-anuncios/")
    doc = parse_html(page)
    article = doc.find("article", id=f"anuncio-{offer.pk}")
    assert "Aguardando aprovação" in article.text
    assert texts.PENDING_NOTICE in page.content.decode()
    # Aguardando aprovação: só "Editar" (nenhum botão de ação).
    assert article.find("button") is None
    assert article.find("a", href=edit_url(offer)) is not None


def test_trusted_seller_offer_is_published_at_once(seller_client):
    response = seller_client.post(NEW_URL, payload())
    offer = Offer.objects.get()
    assert offer.approval == Offer.Approval.APPROVED
    assert offer.approved_at is not None
    assert shown_messages(response) == [texts.OFFER_CREATED]


def test_offer_without_public_contact_says_it_is_not_on_the_showcase(make_seller):
    client = login(make_seller(trusted=True, whatsapp_public=False))
    response = client.post(NEW_URL, payload())
    assert shown_messages(response) == [texts.OFFER_CREATED_NO_CONTACT]


def test_price_accepts_brazilian_formats(seller_client):
    seller_client.post(NEW_URL, payload(price="R$ 1.250,00"))
    assert Offer.objects.get().price_cents == 125000


# Erros: preenchimento preservado (CA8) -----------------------------------------


def test_error_keeps_everything_and_shows_message_next_to_field(seller_client):
    data = payload(
        kind="one_off",
        price="oito reais",
        category=category("servicos").pk,
        variant_name_0="Pequeno",
        variant_price_0="5,00",
    )
    response = seller_client.post(NEW_URL, data)
    assert response.status_code == 200
    assert not Offer.objects.exists()
    assert field_error(response, "price") == texts.PRICE_INVALID
    doc = parse_html(response)
    assert doc.find("title").text.startswith("Erro:")
    assert doc.find("div", role="alert") is not None  # resumo no topo
    assert doc.find("a", href="#id_price") is not None
    # Tudo o que foi digitado volta.
    assert doc.find("input", name="title").get("value") == "Bolo de pote"
    assert doc.find("input", name="price").get("value") == "oito reais"
    assert doc.find("textarea", name="description").text == "Feito no dia."
    assert doc.find("input", name="variant_name_0").get("value") == "Pequeno"
    assert doc.find("input", name="variant_price_0").get("value") == "5,00"
    assert doc.find("input", name="kind", value="one_off").has("checked")
    selected = [
        o for o in doc.find("select", name="category").find_all("option") if o.has("selected")
    ]
    assert [o.text for o in selected] == ["Serviços"]
    price = doc.find("input", name="price")
    assert price.get("aria-invalid") == "true"
    assert "id_price_error" in price.get("aria-describedby")
    assert_accessible_page(response)


def test_required_fields_and_invalid_kind(seller_client):
    response = seller_client.post(NEW_URL, {"kind": "outro"})
    assert response.status_code == 200
    assert not Offer.objects.exists()
    assert field_error(response, "kind") == texts.CHOICE_INVALID
    assert field_error(response, "title") == texts.REQUIRED
    assert field_error(response, "category") == texts.CHOICE_INVALID
    assert field_error(response, "fulfillment") == texts.REQUIRED


def test_variants_are_saved_in_order_and_blank_lines_ignored(seller_client):
    data = payload(
        variant_name_0="Ninho com morango",
        variant_price_0="9",
        variant_name_2="Brigadeiro",
        variant_price_2="7,50",
    )
    seller_client.post(NEW_URL, data)
    offer = Offer.objects.get()
    assert [(v.name, v.price_cents, v.position) for v in offer.variants.all()] == [
        ("Ninho com morango", 900, 0),
        ("Brigadeiro", 750, 1),
    ]


@pytest.mark.parametrize(
    ("line", "field", "message"),
    [
        ({"variant_name_0": "Pequeno"}, "variant_price_0", texts.VARIANT_PRICE_MISSING),
        ({"variant_price_0": "5"}, "variant_name_0", texts.VARIANT_NAME_MISSING),
        ({"variant_name_0": "P", "variant_price_0": "abc"}, "variant_price_0", texts.PRICE_INVALID),
        (
            {"variant_name_0": "Pote", "variant_price_0": "5", "variant_name_1": " pote ",
             "variant_price_1": "6"},
            "variant_name_1",
            texts.VARIANT_NAME_REPEATED,
        ),
    ],
)  # fmt: skip
def test_incomplete_or_repeated_variant_is_an_error(seller_client, line, field, message):
    response = seller_client.post(NEW_URL, payload(**line))
    assert not Offer.objects.exists()
    assert field_error(response, field) == message


# Campos condicionais: o servidor ignora o que não vale (CA8, D20) --------------


def test_non_food_category_ignores_food_fields_even_invalid(seller_client):
    data = payload(
        category=category("servicos").pk,
        portion="x" * 200,  # passa do limite, mas não vale para Serviços
        ingredients="Leite",
        allergens="Contém leite",
    )
    response = seller_client.post(NEW_URL, data)
    assert response.status_code == 302
    offer = Offer.objects.get()
    assert (offer.portion, offer.ingredients, offer.allergens) == ("", "", "")


def test_food_category_saves_food_fields(seller_client):
    data = payload(
        category=category("bebidas").pk,
        portion="300 ml",
        ingredients="Café, leite",
        allergens="Contém leite",
    )
    seller_client.post(NEW_URL, data)
    offer = Offer.objects.get()
    assert (offer.portion, offer.ingredients, offer.allergens) == (
        "300 ml",
        "Café, leite",
        "Contém leite",
    )


def test_food_field_too_long_is_an_error_in_food_category(seller_client):
    response = seller_client.post(NEW_URL, payload(portion="x" * 200))
    assert not Offer.objects.exists()
    assert field_error(response, "portion")


def test_non_daily_ignores_closing_time_and_confirmation(seller_client):
    data = payload(kind="recurring", closing_time="banana", confirm_today="on")
    response = seller_client.post(NEW_URL, data)
    assert response.status_code == 302
    offer = Offer.objects.get()
    assert offer.closing_time is None
    assert offer.daily_confirmed_on is None


@time_machine.travel(NOW, tick=False)
def test_daily_offer_confirmed_on_create_with_closing_time(seller_client, tz):
    data = payload(kind="daily", closing_time="18:00", confirm_today="on")
    seller_client.post(NEW_URL, data)
    offer = Offer.objects.get()
    assert offer.closing_time == time(18, 0)
    assert offer.daily_confirmed_on == timezone.now().astimezone(tz).date()
    page = parse_html(seller_client.get("/meus-anuncios/"))
    article = page.find("article", id=f"anuncio-{offer.pk}")
    assert "Disponível hoje" in article.text
    assert "Confirmado até 18:00" in article.text


@time_machine.travel(NOW, tick=False)
def test_daily_offer_without_confirmation(seller_client):
    seller_client.post(NEW_URL, payload(kind="daily"))
    offer = Offer.objects.get()
    assert offer.daily_confirmed_on is None
    assert offer.closing_time is None


@time_machine.travel(NOW, tick=False)
def test_daily_confirmation_with_closing_time_already_past_is_refused(seller_client):
    data = payload(kind="daily", closing_time="09:30", confirm_today="on")
    response = seller_client.post(NEW_URL, data)
    assert response.status_code == 200
    assert not Offer.objects.exists()
    assert field_error(response, "closing_time") == texts.CLOSING_PASSED


@time_machine.travel(NOW, tick=False)
def test_daily_invalid_time_is_an_error(seller_client):
    response = seller_client.post(NEW_URL, payload(kind="daily", closing_time="25:99"))
    assert not Offer.objects.exists()
    assert field_error(response, "closing_time") == texts.TIME_INVALID


# Editar -------------------------------------------------------------------------


def test_edit_form_shows_current_values(seller_client, make_offer):
    offer = make_offer(
        seller_client.seller,
        title="Brownie",
        price_cents=1250,
        description="Com nozes",
        variants=[("Pequeno", 800)],
    )
    response = seller_client.get(edit_url(offer))
    assert response.status_code == 200
    assert_accessible_page(response)
    doc = parse_html(response)
    assert doc.find("h1").text == texts.OFFER_EDIT_TITLE
    assert doc.find("input", name="title").get("value") == "Brownie"
    assert doc.find("input", name="price").get("value") == "12,50"
    assert doc.find("input", name="variant_name_0").get("value") == "Pequeno"
    assert doc.find("input", name="variant_price_0").get("value") == "8,00"
    assert doc.find("input", name="kind", value="recurring").has("checked")


def test_edit_saves_and_keeps_approval(make_seller, make_offer):
    seller = make_seller(trusted=False)
    offer = make_offer(seller, approval=Offer.Approval.PENDING, variants=[("A", 100)])
    client = login(seller)
    response = client.post(edit_url(offer), payload(title="Novo título", price="11"))
    assert response.status_code == 302
    assert response["Location"] == f"/meus-anuncios/#anuncio-{offer.pk}"
    assert shown_messages(response) == [texts.OFFER_SAVED]
    offer.refresh_from_db()
    assert offer.title == "Novo título"
    assert offer.price_cents == 1100
    assert offer.approval == Offer.Approval.PENDING
    assert not offer.variants.exists()  # linhas em branco apagam as variações


def test_edit_of_approved_offer_stays_approved(seller_client, make_offer):
    offer = make_offer(seller_client.seller)
    seller_client.post(edit_url(offer), payload(title="Outro"))
    offer.refresh_from_db()
    assert offer.approval == Offer.Approval.APPROVED


def test_editing_one_off_renews_confirmation(seller_client, make_offer):
    old = timezone.now() - timedelta(days=20)
    offer = make_offer(seller_client.seller, kind="one_off", last_confirmed_at=old)
    seller_client.post(edit_url(offer), payload(kind="one_off"))
    offer.refresh_from_db()
    assert timezone.now() - offer.last_confirmed_at < timedelta(minutes=1)


def test_changing_sold_one_off_to_recurring_reactivates(seller_client, make_offer):
    offer = make_offer(seller_client.seller, kind="one_off", status=Offer.Status.SOLD)
    seller_client.post(edit_url(offer), payload(kind="recurring"))
    offer.refresh_from_db()
    assert offer.status == Offer.Status.ACTIVE


@time_machine.travel(NOW, tick=False)
def test_editing_daily_can_withdraw_todays_confirmation(seller_client, make_offer, tz):
    today = timezone.now().astimezone(tz).date()
    offer = make_offer(seller_client.seller, kind="daily", daily_confirmed_on=today)
    doc = parse_html(seller_client.get(edit_url(offer)))
    assert doc.find("input", name="confirm_today").has("checked")
    seller_client.post(edit_url(offer), payload(kind="daily"))  # caixa desmarcada
    offer.refresh_from_db()
    assert offer.daily_confirmed_on is None


@time_machine.travel(NOW, tick=False)
def test_editing_confirmed_sold_out_daily_keeps_status(seller_client, make_offer, tz):
    today = timezone.now().astimezone(tz).date()
    offer = make_offer(
        seller_client.seller,
        kind="daily",
        daily_confirmed_on=today,
        status=Offer.Status.SOLD_OUT,
    )
    seller_client.post(edit_url(offer), payload(kind="daily", confirm_today="on"))
    offer.refresh_from_db()
    assert offer.status == Offer.Status.SOLD_OUT
    assert offer.daily_confirmed_on == today


def test_edit_keeps_inactive_current_category(seller_client, make_offer):
    offer = make_offer(seller_client.seller, category="outros")
    Category.objects.filter(slug="outros").update(is_active=False)
    doc = parse_html(seller_client.get(edit_url(offer)))
    selected = [
        o for o in doc.find("select", name="category").find_all("option") if o.has("selected")
    ]
    assert [o.text for o in selected] == ["Outros"]
    response = seller_client.post(edit_url(offer), payload(category=offer.category_id))
    assert response.status_code == 302


def test_csrf_is_enforced_on_offer_form(seller_client):
    client = Client(enforce_csrf_checks=True)
    client.force_login(seller_client.user)
    response = client.post(NEW_URL, payload())
    assert response.status_code == 403
    assert not Offer.objects.exists()


def today_titles() -> list[str]:
    """Títulos em "Disponíveis hoje" na vitrine (`?hoje=1`)."""
    doc = parse_html(Client().get("/", {"hoje": "1"}))
    return [a.find("h3").text for a in doc.find_all("article")]


@time_machine.travel(NOW, tick=False)
@pytest.mark.parametrize("confirmed", [True, False])
def test_editing_hidden_daily_with_confirmation_checked_never_breaks(
    seller_client, make_offer, tz, confirmed
):
    """R1: anúncio oculto não pode ser confirmado; a caixa é ignorada, sem 500."""
    today = timezone.now().astimezone(tz).date()
    offer = make_offer(
        seller_client.seller,
        kind="daily",
        hidden_at=timezone.now(),
        daily_confirmed_on=today if confirmed else None,
    )
    data = payload(kind="daily", title="Novo título", confirm_today="on")
    response = seller_client.post(edit_url(offer), data)
    assert response.status_code == 302
    offer.refresh_from_db()
    assert offer.title == "Novo título"
    assert offer.hidden_at is not None
    assert offer.daily_confirmed_on == (today if confirmed else None)  # nada muda


@time_machine.travel(NOW, tick=False)
def test_edit_race_with_action_not_allowed_shows_error_not_500(
    seller_client, make_offer, monkeypatch
):
    """R1: se o anúncio mudar entre a validação e a gravação, o formulário volta com aviso."""
    offer = make_offer(seller_client.seller, kind="daily", title="Antes")

    def raises(*args, **kwargs):
        raise ActionNotAllowed("confirm_today", "hidden")

    monkeypatch.setattr(services_seller, "update_offer", raises)
    response = seller_client.post(edit_url(offer), payload(kind="daily", confirm_today="on"))
    assert response.status_code == 200
    assert texts.ACTION_FAILED in parse_html(response).find("div", class_="aviso--error").text
    offer.refresh_from_db()
    assert offer.title == "Antes"


@time_machine.travel("2026-11-05 19:00:00-03:00", tick=False)
def test_daily_to_recurring_after_closing_does_not_come_back_as_available(
    seller_client, make_offer, tz
):
    """R2 (a): a confirmação vencida do dia não volta como recorrente até 23h59."""
    today = timezone.now().astimezone(tz).date()
    offer = make_offer(
        seller_client.seller,
        kind="daily",
        title="Bolo de pote",
        daily_confirmed_on=today,
        closing_time=time(18, 0),
    )
    assert today_titles() == []
    response = seller_client.post(edit_url(offer), payload(kind="recurring"))
    assert response.status_code == 302
    offer.refresh_from_db()
    assert offer.kind == Offer.Kind.RECURRING
    assert offer.daily_confirmed_on is None
    assert today_titles() == []


@time_machine.travel(NOW, tick=False)
def test_recurring_confirmed_to_daily_unchecked_leaves_today(seller_client, make_offer, tz):
    """R2 (b): virar oferta do dia com a caixa desmarcada tira de "Disponíveis hoje"."""
    today = timezone.now().astimezone(tz).date()
    offer = make_offer(seller_client.seller, title="Bolo de pote", daily_confirmed_on=today)
    assert today_titles() == ["Bolo de pote"]
    response = seller_client.post(edit_url(offer), payload(kind="daily"))  # caixa desmarcada
    assert response.status_code == 302
    offer.refresh_from_db()
    assert offer.kind == Offer.Kind.DAILY
    assert offer.daily_confirmed_on is None
    assert today_titles() == []


@time_machine.travel(NOW, tick=False)
def test_recurring_confirmed_to_daily_checked_stays_today(seller_client, make_offer, tz):
    today = timezone.now().astimezone(tz).date()
    offer = make_offer(seller_client.seller, title="Bolo de pote", daily_confirmed_on=today)
    seller_client.post(
        edit_url(offer), payload(kind="daily", confirm_today="on", closing_time="18:00")
    )
    offer.refresh_from_db()
    assert offer.daily_confirmed_on == today
    assert offer.closing_time == time(18, 0)
    assert today_titles() == ["Bolo de pote"]


@time_machine.travel("2026-11-05 23:59:00-03:00", tick=False)
def test_daily_confirmation_from_2359_is_refused_in_the_form(seller_client):
    """R4: a caixa "Já confirmar" às 23:59 não teria efeito: o formulário avisa."""
    response = seller_client.post(NEW_URL, payload(kind="daily", confirm_today="on"))
    assert response.status_code == 200
    assert not Offer.objects.exists()
    assert field_error(response, "confirm_today") == texts.CONFIRM_DAY_OVER
    # Sem a caixa, salva normalmente.
    assert seller_client.post(NEW_URL, payload(kind="daily")).status_code == 302


def test_sold_out_becoming_one_off_is_active(seller_client, make_offer, tz):
    """R5: venda única não tem "esgotado": ao virar venda única, volta a ficar ativa."""
    offer = make_offer(seller_client.seller, status=Offer.Status.SOLD_OUT)
    seller_client.post(edit_url(offer), payload(kind="one_off"))
    offer.refresh_from_db()
    assert offer.kind == Offer.Kind.ONE_OFF
    assert offer.status == Offer.Status.ACTIVE
    assert "sold" in services_seller.offer_actions(
        offer, timezone.now(), tz, settings.RECONFIRM_DAYS
    )


def test_one_off_help_uses_reconfirm_days(seller_client, settings):
    """R6: o prazo da venda única vem de RECONFIRM_DAYS."""
    settings.RECONFIRM_DAYS = 9
    doc = parse_html(seller_client.get(NEW_URL))
    help_texts = [s.text for s in doc.find_all("span", class_="legenda")]
    assert any("a cada 9 dias" in t for t in help_texts)
    assert not any("{dias}" in t for t in help_texts)


# Teto de anúncios (S1) ---------------------------------------------------------------


def test_seller_cannot_pass_30_offers(seller_client, make_offer):
    for n in range(services_seller.MAX_OFFERS_PER_SELLER):
        make_offer(seller_client.seller, title=f"Anúncio {n}")
    response = seller_client.post(NEW_URL, payload(title="Mais um"))
    assert response.status_code == 200
    message = texts.OFFER_LIMIT_REACHED.format(max=30)
    assert message in parse_html(response).find("div", class_="aviso--error").text
    assert parse_html(response).find("input", name="title").get("value") == "Mais um"
    assert Offer.objects.filter(seller=seller_client.seller).count() == 30
    assert not Offer.objects.filter(title="Mais um").exists()


def test_untrusted_seller_can_have_at_most_3_pending(make_seller, make_offer):
    seller = make_seller(trusted=False)
    client = login(seller)
    for n in range(2):
        make_offer(seller, title=f"Pendente {n}", approval=Offer.Approval.PENDING)
    assert client.post(NEW_URL, payload(title="Terceiro")).status_code == 302
    response = client.post(NEW_URL, payload(title="Quarto"))
    assert response.status_code == 200
    message = texts.PENDING_LIMIT_REACHED.format(max=3)
    assert message in parse_html(response).find("div", class_="aviso--error").text
    assert not Offer.objects.filter(title="Quarto").exists()


def test_trusted_seller_is_not_limited_by_pending(seller_client, make_offer):
    for n in range(5):
        make_offer(seller_client.seller, title=f"P{n}", approval=Offer.Approval.PENDING)
    assert seller_client.post(NEW_URL, payload()).status_code == 302
