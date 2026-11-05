"""Página inicial: busca, filtros, "Disponíveis hoje", rodízio, paginação (CA1-CA3, CA17)."""

import io
from datetime import date, time, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import time_machine
from django.core.files.base import ContentFile

from apps.catalog.domain.ordering import order_offers
from apps.catalog.models import Category, Offer, OfferPhoto
from apps.core import clock
from apps.core.testing import (
    assert_accessible_page,
    assert_no_set_cookie,
    assert_phone_absent,
    assert_single_link_per_article,
    parse_html,
)
from apps.metrics.models import DailySearchMiss
from conftest import DEFAULT_WHATSAPP

pytestmark = pytest.mark.django_db

NOW = "2026-11-05 12:00:00-03:00"
TODAY = date(2026, 11, 5)
BROWSER = {"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile"}


@pytest.fixture(autouse=True)
def frozen_clock():
    with time_machine.travel(NOW, tick=False):
        yield


def card_ids(response) -> list[int]:
    doc = parse_html(response)
    return [int(a.get("id").removeprefix("oferta-")) for a in doc.find_all("article")]


def card_link(response, offer_id: int) -> str:
    article = parse_html(response).find("article", id=f"oferta-{offer_id}")
    return article.find("a").get("href")


def check_public(response) -> None:
    assert response.status_code == 200
    assert_accessible_page(response)
    assert_phone_absent(response, DEFAULT_WHATSAPP)
    assert_no_set_cookie(response)


def test_home_lists_public_offers_without_js_or_cookie(client, make_offer):
    offer = make_offer(title="Bolo de pote")
    response = client.get("/")
    check_public(response)
    assert card_ids(response) == [offer.pk]
    assert_single_link_per_article(response)
    doc = parse_html(response)
    # Faixa da página inicial: h1 e busca no cabeçalho, busca como formulário GET.
    assert doc.find("header").find("h1").text == "O que tem no campus hoje?"
    form = doc.find("form", role="search")
    assert (form.get("method"), form.get("action")) == ("get", "/")
    assert doc.find("h2", id="lista-titulo").text == "Ofertas"


def test_home_hides_offers_that_are_not_public(client, make_offer, make_seller, make_user):
    visible = make_offer()
    make_offer(approval=Offer.Approval.PENDING)
    make_offer(status=Offer.Status.PAUSED)
    make_offer(hidden_at=clock.now())
    make_offer(seller=make_seller(whatsapp_public=False))  # D4: sem autorização, não é público
    make_offer(seller=make_seller(whatsapp_number=""))
    make_offer(seller=make_seller(user=make_user(is_active=False)))
    make_offer(kind=Offer.Kind.ONE_OFF, last_confirmed_at=clock.now() - timedelta(days=14))
    make_offer(
        kind=Offer.Kind.ONE_OFF,
        status=Offer.Status.SOLD,
        status_changed_at=clock.now() - timedelta(days=1),
    )
    response = client.get("/")
    assert card_ids(response) == [visible.pk]


def test_sold_today_and_sold_out_stay_listed_with_state(client, make_offer):
    sold = make_offer(
        kind=Offer.Kind.ONE_OFF, status=Offer.Status.SOLD, status_changed_at=clock.now()
    )
    sold_out = make_offer(status=Offer.Status.SOLD_OUT)
    response = client.get("/")
    doc = parse_html(response)
    sold_card = doc.find("article", id=f"oferta-{sold.pk}")
    assert "Vendido" in sold_card.text
    assert sold_card.find("span", class_="preco--riscado") is not None
    assert "Esgotado" in doc.find("article", id=f"oferta-{sold_out.pk}").text


def test_search_matches_title_seller_and_description_without_accents(
    client, make_offer, make_seller
):
    by_title = make_offer(title="Pão de queijo")
    by_seller = make_offer(
        seller=make_seller(display_name="Queijo Mineiro da Bia"), title="Coxinha"
    )
    by_body = make_offer(title="Lanche", description="Com queijo minas")
    make_offer(title="Brigadeiro")
    response = client.get("/", {"q": "QUEIJO"})
    check_public(response)
    ids = card_ids(response)
    # Título primeiro, depois vendedor, depois o resto (D13).
    assert ids == [by_title.pk, by_seller.pk, by_body.pk]
    assert parse_html(response).find("h2", id="lista-titulo").text == "Resultados para “QUEIJO”"
    assert parse_html(response).find("input", name="q").get("value") == "QUEIJO"


def test_search_matches_variant_and_category(client, make_offer):
    by_variant = make_offer(title="Cookie", variants=[("Chocolate meio amargo", 700)])
    by_category = make_offer(title="Aula", category="servicos")
    assert card_ids(client.get("/", {"q": "amargo"})) == [by_variant.pk]
    assert card_ids(client.get("/", {"q": "servicos"})) == [by_category.pk]


def test_category_filter_keeps_search_and_today_in_links(client, make_offer):
    food = make_offer(title="Bolo", daily_confirmed_on=TODAY)
    make_offer(title="Bolo de aniversário", category="servicos", daily_confirmed_on=TODAY)
    response = client.get("/", {"q": "bolo", "cat": "comidas-e-doces", "hoje": "1"})
    assert card_ids(response) == [food.pk]
    doc = parse_html(response)
    chips = {a.text: a for a in doc.find("nav", aria_label="Categorias").find_all("a")}
    assert chips["Comidas e doces"].get("aria-current") == "true"
    assert parse_qs(urlsplit(chips["Tudo"].get("href")).query) == {"q": ["bolo"], "hoje": ["1"]}
    services = parse_qs(urlsplit(chips["Serviços"].get("href")).query)
    assert services == {"q": ["bolo"], "cat": ["servicos"], "hoje": ["1"]}
    # O formulário de busca repete cat e hoje em campos ocultos.
    search = doc.find("form", role="search")
    assert search.find("input", name="cat").get("value") == "comidas-e-doces"
    assert search.find("input", name="hoje").get("value") == "1"


def test_today_filter_shows_only_confirmed_and_toggles(client, make_offer):
    confirmed = make_offer(daily_confirmed_on=TODAY)
    make_offer(kind=Offer.Kind.DAILY, daily_confirmed_on=TODAY, closing_time=time(11, 0))
    make_offer(daily_confirmed_on=TODAY - timedelta(days=1))
    response = client.get("/", {"hoje": "1"})
    assert card_ids(response) == [confirmed.pk]
    doc = parse_html(response)
    today = doc.find("a", class_="chip--hoje")
    assert today.get("aria-current") == "true"
    assert today.get("href") == "/"  # clicar de novo remove o filtro
    assert doc.find("h2", id="lista-titulo").text == "Disponíveis hoje"


def test_unknown_category_is_ignored(client, make_offer):
    offer = make_offer()
    inactive = Category.objects.create(name="Antiga", slug="antiga", is_active=False)
    assert card_ids(client.get("/", {"cat": "nao-existe"})) == [offer.pk]
    assert card_ids(client.get("/", {"cat": inactive.slug})) == [offer.pk]


def test_card_links_carry_list_context_and_anchor(client, make_offer):
    offers = [make_offer(title=f"Bolo {i}") for i in range(3)]
    response = client.get("/", {"q": "bolo", "cat": "comidas-e-doces", "hoje": "", "pagina": "2"})
    for offer in offers:
        link = urlsplit(card_link(response, offer.pk))
        assert link.path == f"/oferta/{offer.pk}/"
        assert parse_qs(link.query) == {"q": ["bolo"], "cat": ["comidas-e-doces"], "pagina": ["2"]}
        assert parse_html(response).find("article", id=f"oferta-{offer.pk}") is not None


def test_card_shows_photo_or_placeholder_price_from_seller_and_fulfillment(
    client, make_offer, make_seller
):
    seller = make_seller(display_name="Doces da Ana")
    with_photo = make_offer(
        seller=seller, title="Brownie", fulfillment="Retirada no bloco 3", variants=[("Nozes", 900)]
    )
    OfferPhoto.objects.create(
        offer=with_photo,
        position=0,
        card_image=ContentFile(b"card", name="x.webp"),
        page_image=ContentFile(b"page", name="y.webp"),
        page_width=800,
        page_height=600,
    )
    without = make_offer(seller=seller, title="Cookie")
    doc = parse_html(client.get("/"))

    card = doc.find("article", id=f"oferta-{with_photo.pk}")
    img = card.find("img")
    assert img.get("src").endswith("-card.webp")
    assert (img.get("width"), img.get("height")) == ("480", "480")
    assert "A partir de" in card.text and "R$ 9,00" in card.text
    assert "Doces da Ana · Retirada no bloco 3" in card.text
    assert card.find("h3").text == "Brownie"

    placeholder = doc.find("article", id=f"oferta-{without.pk}")
    assert placeholder.find("img") is None
    assert placeholder.find("div", class_="foto--vazia") is not None
    assert "A partir de" not in placeholder.text


def test_order_is_daily_shuffle_and_stable(client, make_offer):
    offers = [make_offer() for _ in range(8)]
    expected = [o.pk for o in order_offers([(None, o) for o in offers], TODAY)]
    assert card_ids(client.get("/")) == expected
    assert card_ids(client.get("/")) == expected  # estável no mesmo dia
    with time_machine.travel("2026-11-06 12:00:00-03:00", tick=False):
        tomorrow = [o.pk for o in order_offers([(None, o) for o in offers], date(2026, 11, 6))]
        assert card_ids(client.get("/")) == tomorrow
    assert expected != tomorrow


def test_day_of_shuffle_uses_community_timezone(client, make_offer):
    offers = [make_offer() for _ in range(6)]
    # 22:00 em São Paulo já é dia 6 em UTC; a semente continua sendo o dia 5.
    with time_machine.travel("2026-11-05 22:00:00-03:00", tick=False):
        expected = [o.pk for o in order_offers([(None, o) for o in offers], TODAY)]
        assert card_ids(client.get("/")) == expected


def test_cumulative_pages_of_20_with_more_link(client, make_offer):
    offers = [make_offer() for _ in range(45)]
    order = [o.pk for o in order_offers([(None, o) for o in offers], TODAY)]

    first = client.get("/")
    assert card_ids(first) == order[:20]
    links = [a for a in parse_html(first).find_all("a") if a.text == "Mostrar mais ofertas"]
    assert len(links) == 1
    href = urlsplit(links[0].get("href"))
    assert parse_qs(href.query) == {"pagina": ["2"]}
    assert href.fragment == f"oferta-{order[20]}"

    second = client.get("/", {"pagina": "2"})
    assert card_ids(second) == order[:40]
    third = client.get("/", {"pagina": "3"})
    assert card_ids(third) == order
    assert not [a for a in parse_html(third).find_all("a") if a.text == "Mostrar mais ofertas"]


@pytest.mark.parametrize("pagina", ["abc", "-3", "0", "", "99999"])
def test_invalid_page_falls_back(client, make_offer, pagina):
    make_offer()
    response = client.get("/", {"pagina": pagina})
    assert response.status_code == 200
    assert len(card_ids(response)) == 1


def test_empty_state_without_offers(client):
    response = client.get("/")
    check_public(response)
    doc = parse_html(response)
    assert doc.find("h2", id="vazio-titulo").text == "Ainda não há ofertas por aqui"
    assert doc.find("section", class_="vazio").find("a").get("href") == "/cadastrar/"


def test_search_without_result_shows_clear_filters_and_records_term(client, make_offer):
    make_offer(title="Bolo")
    response = client.get("/", {"q": "  Pão   de QUEIJO "}, headers=BROWSER)
    check_public(response)
    empty = parse_html(response).find("section", class_="vazio")
    assert empty.find("h2").text == "Nada encontrado para “Pão de QUEIJO”"
    clear = empty.find("a")
    assert (clear.text, clear.get("href")) == ("Limpar filtros", "/")
    miss = DailySearchMiss.objects.get()
    assert (miss.date, miss.term, miss.count) == (TODAY, "pao de queijo", 1)
    client.get("/", {"q": "pao de queijo"}, headers=BROWSER)
    assert DailySearchMiss.objects.get().count == 2


def test_search_miss_not_recorded_for_robots_head_or_results(client, make_offer):
    make_offer(title="Bolo")
    client.get("/", {"q": "nada"}, headers={"user-agent": "Googlebot/2.1"})
    client.head("/", {"q": "nada"}, headers=BROWSER)
    client.get("/", {"q": "bolo"}, headers=BROWSER)
    assert not DailySearchMiss.objects.exists()


def test_search_miss_only_recorded_for_pure_search(client, make_offer):
    """R9: com categoria ou "hoje", o vazio pode ser culpa do filtro: não conta."""
    make_offer(title="Bolo")
    client.get("/", {"q": "nada", "cat": "bebidas"}, headers=BROWSER)
    client.get("/", {"q": "nada", "hoje": "1"}, headers=BROWSER)
    assert not DailySearchMiss.objects.exists()
    client.get("/", {"q": "nada"}, headers=BROWSER)
    assert DailySearchMiss.objects.get().term == "nada"


def test_control_characters_never_reach_the_search(client, make_offer):
    """Q1: o termo exibido e o gravado ficam sem caracteres de controle."""
    make_offer(title="Bolo de pote")
    response = client.get("/", {"q": "bolo\x00de\x07pote"}, headers=BROWSER)
    assert response.status_code == 200
    assert "\x00" not in response.content.decode()
    assert card_ids(response)  # "bolo de pote" ainda acha a oferta


def test_today_filter_without_result_has_its_own_message(client, make_offer):
    make_offer()
    empty = parse_html(client.get("/", {"hoje": "1"})).find("section", class_="vazio")
    assert empty.find("h2").text == "Ninguém confirmou oferta para hoje ainda"
    assert empty.find("a").text == "Limpar filtros"


def test_demo_data_is_listed(client, settings):
    from django.core.management import call_command

    settings.DEMO_DATA = True
    call_command("load_demo", stdout=io.StringIO())
    response = client.get("/")
    check_public(response)
    titles = [a.find("h3").text for a in parse_html(response).find_all("article")]
    assert "Cookies caseiros (exemplo)" in titles
    assert "Revisão de provas (exemplo)" not in titles  # pendente
    assert "Mochila (exemplo)" not in titles  # pausado
    assert all("(exemplo)" in t for t in titles)


def test_demo_data_is_not_public_when_demo_data_is_off(client, settings, make_offer):
    """R3: desligar DEMO_DATA tira a demonstração da vitrine na hora."""
    from django.core.management import call_command

    settings.DEMO_DATA = True
    call_command("load_demo", stdout=io.StringIO())
    real = make_offer(title="Bolo de verdade")
    demo = Offer.objects.get(title="Cookies caseiros (exemplo)")
    settings.DEMO_DATA = False
    response = client.get("/")
    titles = [a.find("h3").text for a in parse_html(response).find_all("article")]
    assert titles == ["Bolo de verdade"]
    assert not card_ids(client.get("/", {"q": "cookies"}))
    assert client.get(f"/oferta/{demo.pk}/").status_code == 404
    assert client.get(f"/vendedor/{demo.seller.slug}/").status_code == 404
    assert client.get(f"/oferta/{demo.pk}/denunciar/").status_code == 404
    assert client.get(f"/oferta/{real.pk}/").status_code == 200
