"""Página da oferta (CA1, CA2, CA4, CA6, CA16)."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import time_machine
from django.core.files.base import ContentFile

from apps.catalog.models import Offer, OfferPhoto
from apps.core import clock
from apps.core.testing import (
    assert_accessible_page,
    assert_no_set_cookie,
    assert_phone_absent,
    parse_html,
)
from apps.metrics.models import DailyOfferStat
from conftest import DEFAULT_WHATSAPP

pytestmark = pytest.mark.django_db

BROWSER = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"}


@pytest.fixture(autouse=True)
def frozen_clock():
    with time_machine.travel("2026-11-05 12:00:00-03:00", tick=False):
        yield


def url(offer) -> str:
    return f"/oferta/{offer.pk}/"


def add_photo(offer, position: int, w: int = 800, h: int = 600) -> OfferPhoto:
    return OfferPhoto.objects.create(
        offer=offer,
        position=position,
        card_image=ContentFile(b"card", name="c.webp"),
        page_image=ContentFile(b"page", name="p.webp"),
        page_width=w,
        page_height=h,
    )


def check_public(response) -> None:
    assert response.status_code == 200
    assert_accessible_page(response)
    assert_phone_absent(response, DEFAULT_WHATSAPP)
    assert_no_set_cookie(response)


def test_offer_page_shows_everything_the_buyer_needs(client, make_offer, make_seller):
    seller = make_seller(display_name="Doces da Ana")
    offer = make_offer(
        seller=seller,
        title="Bolo de pote",
        description="Feito no dia.",
        fulfillment="Retirada no bloco 3",
        price_cents=800,
        variants=[("Ninho", 800), ("Brigadeiro", 700)],
    )
    response = client.get(url(offer))
    check_public(response)
    doc = parse_html(response)
    main = doc.find("main")
    assert main.find("h1").text == "Bolo de pote"
    assert "Sob encomenda" in main.text
    assert "A partir de R$ 7,00" in main.text
    assert "Retirada no bloco 3" in main.text
    assert "Feito no dia." in main.text
    seller_link = main.find("a", href=f"/vendedor/{seller.slug}/")
    assert seller_link.text == "Doces da Ana"
    assert "Abrir o WhatsApp não é um pedido confirmado" in main.text
    report = main.find("a", href=f"/oferta/{offer.pk}/denunciar/")
    assert report.text == "Denunciar esta oferta"


def test_contact_form_is_a_get_to_whatsapp_route_with_variants(client, make_offer):
    offer = make_offer(variants=[("Ninho", 800), ("Brigadeiro", 700)])
    doc = parse_html(client.get(url(offer)))
    form = doc.find("form", action=f"/oferta/{offer.pk}/whatsapp/")
    assert form.get("method") == "get"
    assert "nofollow" in form.get("rel").split()
    radios = form.find_all("input", type="radio")
    assert [r.get("name") for r in radios] == ["variacao", "variacao"]
    assert [int(r.get("value")) for r in radios] == [v.pk for v in offer.variants.all()]
    assert not any(r.has("checked") for r in radios)  # nenhuma = mensagem só com o nome
    assert form.find("legend").text == "Escolha uma opção (opcional)"
    assert form.find("button", type="submit").text == "Consultar no WhatsApp"
    assert form.find("p", class_="aviso-contato") is not None


def test_contact_form_without_variants_has_only_the_button(client, make_offer):
    offer = make_offer()
    form = parse_html(client.get(url(offer))).find("form", action=f"/oferta/{offer.pk}/whatsapp/")
    assert form.find("fieldset") is None
    assert form.find("button").text == "Consultar no WhatsApp"


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (Offer.Status.SOLD_OUT, "Esta oferta está esgotada no momento."),
        (Offer.Status.SOLD, "Esta oferta já foi vendida."),
    ],
)
def test_sold_out_and_sold_have_no_contact_button(client, make_offer, status, message):
    kind = Offer.Kind.ONE_OFF if status == Offer.Status.SOLD else Offer.Kind.RECURRING
    offer = make_offer(kind=kind, status=status, status_changed_at=clock.now() - timedelta(days=3))
    response = client.get(url(offer))
    check_public(response)
    main = parse_html(response).find("main")
    assert main.find("form", action=f"/oferta/{offer.pk}/whatsapp/") is None
    assert message in main.text
    assert f"Ver outras ofertas de {offer.seller.display_name}" in main.text
    struck = main.find("span", class_="preco--riscado")
    assert (struck is not None) == (status == Offer.Status.SOLD)


def test_daily_sold_out_badge_only_on_the_day_it_was_marked(client, make_offer):
    """Decisão do dono: "Esgotado" da oferta do dia some no dia seguinte (fica sem selo)."""
    today = make_offer(
        kind=Offer.Kind.DAILY, status=Offer.Status.SOLD_OUT, status_changed_at=clock.now()
    )
    yesterday = make_offer(
        kind=Offer.Kind.DAILY,
        status=Offer.Status.SOLD_OUT,
        status_changed_at=clock.now() - timedelta(days=1),
    )
    home = parse_html(client.get("/"))
    assert "Esgotado" in home.find("article", id=f"oferta-{today.pk}").text
    assert "Esgotado" not in home.find("article", id=f"oferta-{yesterday.pk}").text
    # A página continua sem botão e explica por quê.
    main = parse_html(client.get(url(yesterday))).find("main")
    assert main.find("form", action=f"/oferta/{yesterday.pk}/whatsapp/") is None
    assert "Esta oferta está esgotada no momento." in main.text


def test_food_block_shows_not_informed_for_empty_fields(client, make_offer):
    offer = make_offer(portion="1 pote de 200 g", ingredients="", allergens="  ")
    doc = parse_html(client.get(url(offer)))
    block = doc.find("section", class_="oferta-pagina__alimento")
    assert block.find("h2").text == "Sobre este alimento"
    pairs = dict(zip([d.text for d in block.find_all("dt")], block.find_all("dd"), strict=True))
    assert pairs["Porção"].text == "1 pote de 200 g"
    assert pairs["Ingredientes"].text == "Não informado pelo vendedor"
    assert pairs["Alergênicos"].text == "Não informado pelo vendedor"
    assert "Confirme com a pessoa se tiver alergia" in block.text


def test_food_block_absent_outside_food_categories(client, make_offer):
    offer = make_offer(category="servicos", portion="ignorado")
    doc = parse_html(client.get(url(offer)))
    assert doc.find("section", class_="oferta-pagina__alimento") is None
    assert "Não informado pelo vendedor" not in doc.text


def test_photos_first_large_with_priority_and_alt(client, make_offer):
    offer = make_offer(title="Brownie")
    add_photo(offer, 0, 1280, 960)
    add_photo(offer, 1)
    doc = parse_html(client.get(url(offer)))
    imgs = doc.find("main").find_all("img")
    assert [i.get("alt") for i in imgs] == ["Foto de Brownie", "Foto 2 de Brownie"]
    assert imgs[0].get("fetchpriority") == "high"
    assert (imgs[0].get("width"), imgs[0].get("height")) == ("1280", "960")
    assert imgs[1].get("loading") == "lazy"
    assert all(i.get("src").endswith("-page.webp") for i in imgs)


def test_offer_without_photo_shows_placeholder(client, make_offer):
    doc = parse_html(client.get(url(make_offer())))
    holder = doc.find("main").find("div", class_="foto--vazia")
    assert holder is not None
    assert "Sem foto" in holder.text
    assert doc.find("main").find("img") is None


def test_back_link_rebuilds_list_context_only_with_the_four_params(client, make_offer):
    offer = make_offer()
    response = client.get(
        url(offer), {"q": "bolo", "cat": "bebidas", "hoje": "1", "pagina": "3", "x": "evil"}
    )
    back = parse_html(response).find("a", class_="voltar")
    link = urlsplit(back.get("href"))
    assert link.path == "/"
    assert parse_qs(link.query) == {
        "q": ["bolo"],
        "cat": ["bebidas"],
        "hoje": ["1"],
        "pagina": ["3"],
    }
    assert link.fragment == f"oferta-{offer.pk}"


def test_back_link_without_context_goes_home_with_anchor(client, make_offer):
    offer = make_offer()
    back = parse_html(client.get(url(offer))).find("a", class_="voltar")
    assert back.get("href") == f"/#oferta-{offer.pk}"


def test_back_link_escapes_injected_values(client, make_offer):
    offer = make_offer()
    response = client.get(url(offer), {"q": '"><script>alert(1)</script>', "cat": "a b"})
    assert "<script>alert(1)" not in response.content.decode()
    link = urlsplit(parse_html(response).find("a", class_="voltar").get("href"))
    assert "cat" not in parse_qs(link.query)


@pytest.mark.parametrize(
    "change",
    [
        {"approval": Offer.Approval.PENDING},
        {"status": Offer.Status.PAUSED},
        {"hidden": True},
        {"one_off_expired": True},
    ],
)
def test_unavailable_offer_is_404_with_context(client, make_offer, change):
    fields = {}
    if change.get("hidden"):
        fields["hidden_at"] = clock.now()
    elif change.get("one_off_expired"):
        fields["kind"] = Offer.Kind.ONE_OFF
        fields["last_confirmed_at"] = clock.now() - timedelta(days=14)
    else:
        fields.update(change)
    offer = make_offer(**fields)
    response = client.get(url(offer))
    assert response.status_code == 404
    doc = parse_html(response)
    assert doc.find("h1").text == "Esta oferta não está mais disponível"
    assert "Ela pode ter sido vendida, pausada ou removida." in doc.text
    assert doc.find("main").find("a").text == "Ver outras ofertas"
    assert offer.title not in response.content.decode()
    assert_phone_absent(response, DEFAULT_WHATSAPP)


def test_offer_of_seller_without_authorization_is_404(client, make_offer, make_seller):
    """D4: sem autorização do WhatsApp, o anúncio não é público (CA6)."""
    offer = make_offer(seller=make_seller(whatsapp_public=False))
    response = client.get(url(offer))
    assert response.status_code == 404
    assert_phone_absent(response, DEFAULT_WHATSAPP)


def test_revoking_authorization_takes_offer_down_immediately(client, make_offer):
    offer = make_offer()
    assert client.get(url(offer)).status_code == 200
    offer.seller.whatsapp_public = False
    offer.seller.save()
    assert client.get(url(offer)).status_code == 404


def test_missing_offer_is_404(client):
    assert client.get("/oferta/999999/").status_code == 404


def test_view_is_counted_once_per_get_for_browsers(client, make_offer):
    offer = make_offer()
    client.get(url(offer), headers=BROWSER)
    client.get(url(offer), headers=BROWSER)
    stat = DailyOfferStat.objects.get(offer=offer)
    assert (str(stat.date), stat.views, stat.whatsapp_clicks) == ("2026-11-05", 2, 0)


@pytest.mark.parametrize(
    "agent",
    [
        "",
        "WhatsApp/2.23.20.0 A",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "facebookexternalhit/1.1",
        "Mozilla/5.0 (compatible; SomeCrawler/1.0)",
        "TelegramBot (like TwitterBot)",
        "Slackbot-LinkExpanding 1.0",
        "Mozilla/5.0 LinkPreview/1.0",
        "Baiduspider",
    ],
)
def test_robots_and_link_previews_do_not_count(client, make_offer, agent):
    offer = make_offer()
    assert client.get(url(offer), headers={"user-agent": agent}).status_code == 200
    assert not DailyOfferStat.objects.exists()


def test_head_and_own_seller_do_not_count(client, make_offer):
    offer = make_offer()
    assert client.head(url(offer), headers=BROWSER).status_code == 200
    client.force_login(offer.seller.user)
    assert client.get(url(offer), headers=BROWSER).status_code == 200
    assert not DailyOfferStat.objects.exists()


def test_view_uses_community_day(client, make_offer):
    offer = make_offer()
    with time_machine.travel("2026-11-05 22:30:00-03:00", tick=False):  # já é dia 6 em UTC
        client.get(url(offer), headers=BROWSER)
    assert str(DailyOfferStat.objects.get().date) == "2026-11-05"


def test_post_is_not_allowed(client, make_offer):
    assert client.post(url(make_offer())).status_code == 405
