"""Os 6 fluxos essenciais do brief (seção 10.2), de ponta a ponta com `Client`.

Cada teste conta uma história inteira, como uma pessoa a viveria, e confere o
reflexo na vitrine a cada passo. Comportamento, não layout: status,
redirecionamentos, banco, textos e atributos essenciais do HTML.
"""

import re
from datetime import date, time
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
import time_machine
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.accounts.models import User
from apps.catalog.domain.actions import ACTIONS
from apps.catalog.models import Category, Offer, OfferPhoto, OfferVariant, Seller
from apps.catalog.presenters import anchor_id
from apps.core.testing import (
    assert_accessible_page,
    assert_no_set_cookie,
    assert_phone_absent,
    parse_html,
)
from apps.metrics.models import DailyOfferStat
from apps.moderation.models import Report
from conftest import DEFAULT_WHATSAPP

pytestmark = pytest.mark.django_db

BROWSER = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"}
HOJE = date(2026, 11, 5)
PASSWORD = "pao-de-queijo-quentinho"


@pytest.fixture(autouse=True)
def relogio():
    with time_machine.travel("2026-11-05 12:00:00-03:00", tick=False):
        yield


def categoria(slug: str) -> Category:
    return Category.objects.get(slug=slug)


def titulos(response) -> list[str]:
    """Títulos dos cartões da lista, na ordem em que aparecem."""
    doc = parse_html(response)
    return [h.text for h in doc.find_all("h3", class_="cartao-oferta__titulo")]


def link_do_cartao(response, offer) -> str:
    doc = parse_html(response)
    card = doc.find("article", id=anchor_id(offer.pk))
    assert card is not None, f"cartão de {offer.title!r} não está na lista"
    return card.find("a").get("href")


def erro_do_campo(response, name: str) -> str:
    el = parse_html(response).find(id=f"id_{name}_error")
    return el.text if el is not None else ""


def valor(doc, name: str) -> str | None:
    return doc.find("input", name=name).get("value")


def texto_da_area(doc, name: str) -> str:
    return doc.find("textarea", name=name).text


def mensagem_do_whatsapp(response) -> str:
    assert response.status_code == 302
    location = response["Location"]
    parts = urlsplit(location)
    assert (parts.scheme, parts.netloc) == ("https", "wa.me")
    assert parts.path == f"/{DEFAULT_WHATSAPP}"
    return parse_qs(parts.query)["text"][0]


# Fluxo 1 ---------------------------------------------------------------------


def test_fluxo_visitante_busca_filtra_abre_a_oferta_e_chega_ao_whatsapp(
    client, make_seller, make_offer
):
    ana = make_seller(display_name="Doces da Ana")
    bolo = make_offer(
        ana,
        title="Bolo de pote",
        kind=Offer.Kind.DAILY,
        daily_confirmed_on=HOJE,
        fulfillment="Retirada no bloco 3",
        variants=[("Ninho", 800), ("Brigadeiro", 700)],
    )
    cookie = make_offer(ana, title="Cookie de chocolate")
    make_offer(
        make_seller(display_name="Bruno"), title="Apostila de Cálculo", category="objetos-e-usados"
    )

    # 1. Chega na página inicial sem cadastro e sem cookie.
    home = client.get("/", headers=BROWSER)
    assert home.status_code == 200
    assert_accessible_page(home)
    assert_no_set_cookie(home)
    assert set(titulos(home)) == {"Bolo de pote", "Cookie de chocolate", "Apostila de Cálculo"}

    # 2. Busca pelo nome da vendedora: acha as duas ofertas dela e só elas.
    por_vendedora = client.get("/", {"q": "ana"}, headers=BROWSER)
    assert set(titulos(por_vendedora)) == {"Bolo de pote", "Cookie de chocolate"}
    # Busca com acento e maiúscula acha o título sem acento digitado.
    assert titulos(client.get("/", {"q": "CALCULO"})) == ["Apostila de Cálculo"]

    # 3. Filtra por categoria e por "Disponíveis hoje" (links, sem JavaScript).
    doc = parse_html(home)
    chip = next(a for a in doc.find_all("a", class_="chip") if a.text == "Comidas e doces")
    comidas = client.get(chip.get("href"))
    assert set(titulos(comidas)) == {"Bolo de pote", "Cookie de chocolate"}
    chip_hoje = parse_html(comidas).find("a", class_="chip--hoje")
    hoje = client.get(chip_hoje.get("href"))
    assert titulos(hoje) == ["Bolo de pote"]
    assert "Disponível hoje" in hoje.content.decode()

    # 4. O cartão é um link só e leva o contexto (CA2); abre a oferta.
    href = link_do_cartao(hoje, bolo)
    contexto = parse_qs(urlsplit(href).query)
    assert contexto["hoje"] == ["1"] and contexto["cat"] == ["comidas-e-doces"]
    pagina = client.get(href, headers=BROWSER)
    assert pagina.status_code == 200
    assert_accessible_page(pagina)
    assert_phone_absent(pagina, DEFAULT_WHATSAPP)
    detalhe = parse_html(pagina)
    assert detalhe.find("h1").text == "Bolo de pote"
    voltar = detalhe.find("a", class_="voltar")
    assert voltar.get("href").endswith(f"#{anchor_id(bolo.pk)}")
    assert "hoje=1" in voltar.get("href")

    # 5. Escolhe a variação "Brigadeiro" e envia o formulário (GET, como o navegador).
    form = detalhe.find("form", action=f"/oferta/{bolo.pk}/whatsapp/")
    rotulos = {lab.get("for"): lab.text for lab in detalhe.find_all("label")}
    radio = next(
        r for r in form.find_all("input", type="radio") if "Brigadeiro" in rotulos[r.get("id")]
    )
    query = urlencode({radio.get("name"): radio.get("value")})
    resposta = client.get(f"{form.get('action')}?{query}", headers=BROWSER)

    # 6. 302 para o wa.me com a mensagem pronta (oferta + variação + endereço).
    mensagem = mensagem_do_whatsapp(resposta)
    assert mensagem == (
        "Oi! Vi “Bolo de pote”, opção “Brigadeiro” no Pão de Cada Dia. Ainda está disponível?\n"
        f"http://testserver/oferta/{bolo.pk}/"
    )
    assert_no_set_cookie(resposta)
    stat = DailyOfferStat.objects.get(offer=bolo)
    assert (stat.views, stat.whatsapp_clicks) == (1, 1)

    # Sem escolher variação, a mensagem leva só o nome da oferta.
    sem_variacao = client.get(f"/oferta/{cookie.pk}/whatsapp/")
    assert mensagem_do_whatsapp(sem_variacao).startswith(
        "Oi! Vi “Cookie de chocolate” no Pão de Cada Dia."
    )


# Fluxo 2 ---------------------------------------------------------------------


def test_fluxo_vendedor_cadastra_anuncia_admin_aprova_vendedor_edita_e_pausa(
    staff_client, jpeg_bytes
):
    visitante, vendedor = Client(), Client()

    # 1. Cadastro: entra logado e vai para o painel.
    resposta = vendedor.post(
        "/cadastrar/",
        {
            "display_name": "Doces da Ana",
            "email": "ana@exemplo.test",
            "password": PASSWORD,
            "whatsapp": "(35) 91234-5678",
            "whatsapp_public": "on",
        },
    )
    assert (resposta.status_code, resposta["Location"]) == (302, "/meus-anuncios/")

    # 2. Cria o anúncio com foto. Vai para o painel com confirmação visível.
    resposta = vendedor.post(
        "/meus-anuncios/novo/",
        {
            "kind": "recurring",
            "title": "Bolo de pote",
            "category": categoria("comidas-e-doces").pk,
            "price": "8,50",
            "description": "Feito no dia.",
            "fulfillment": "Retirada no bloco 3",
            "photos": SimpleUploadedFile("bolo.jpg", jpeg_bytes, content_type="image/jpeg"),
        },
        follow=True,
    )
    assert resposta.status_code == 200
    painel = parse_html(resposta)
    assert painel.find("div", class_="aviso--success") is not None
    oferta = Offer.objects.get(title="Bolo de pote")
    assert oferta.approval == Offer.Approval.PENDING
    assert oferta.photos.count() == 1
    assert "Aguardando aprovação" in painel.find("article", id=f"anuncio-{oferta.pk}").text

    # 3. Ainda não existe para o público: nem na lista, nem na página, nem no contato.
    assert titulos(visitante.get("/")) == []
    assert visitante.get(f"/oferta/{oferta.pk}/").status_code == 404
    assert visitante.get(f"/oferta/{oferta.pk}/whatsapp/").status_code == 404
    assert visitante.get("/vendedor/doces-da-ana/").status_code == 200  # a vendedora existe

    # 4. A administração vê na fila e aprova.
    fila = staff_client.get("/admin/")
    assert "Bolo de pote" in fila.content.decode()
    resposta = staff_client.post(f"/admin/anuncios/{oferta.pk}/aprovar/")
    assert resposta.status_code == 302
    oferta.refresh_from_db()
    assert oferta.approval == Offer.Approval.APPROVED
    assert Seller.objects.get(user__email="ana@exemplo.test").is_trusted

    # 5. Agora aparece, com foto, preço e contato.
    home = visitante.get("/")
    assert titulos(home) == ["Bolo de pote"]
    cartao = parse_html(home).find("article", id=anchor_id(oferta.pk))
    assert "R$ 8,50" in cartao.text
    assert cartao.find("img").get("src").endswith(".webp")
    assert visitante.get(f"/oferta/{oferta.pk}/").status_code == 200
    assert visitante.get(f"/oferta/{oferta.pk}/whatsapp/")["Location"].startswith(
        f"https://wa.me/{DEFAULT_WHATSAPP}?text="
    )

    # 6. A vendedora edita título e preço: o reflexo é imediato e a aprovação continua.
    resposta = vendedor.post(
        f"/meus-anuncios/{oferta.pk}/editar/",
        {
            "kind": "recurring",
            "title": "Bolo de pote grande",
            "category": categoria("comidas-e-doces").pk,
            "price": "12,50",
            "description": "Feito no dia.",
            "fulfillment": "Retirada no bloco 3",
        },
        follow=True,
    )
    assert parse_html(resposta).find("div", class_="aviso--success") is not None
    oferta.refresh_from_db()
    assert oferta.approval == Offer.Approval.APPROVED
    assert oferta.photos.count() == 1  # editar sem enviar foto mantém a que já existe
    home = visitante.get("/")
    assert titulos(home) == ["Bolo de pote grande"]
    assert "R$ 12,50" in home.content.decode()
    assert "R$ 8,50" not in home.content.decode()

    # 7. Pausa: some de tudo para o público e fica "Pausado" para ela.
    resposta = vendedor.post(f"/meus-anuncios/{oferta.pk}/acao/", {"action": "pause"}, follow=True)
    assert parse_html(resposta).find("div", class_="aviso--success") is not None
    assert "Pausado" in parse_html(resposta).find("article", id=f"anuncio-{oferta.pk}").text
    assert titulos(visitante.get("/")) == []
    assert visitante.get(f"/oferta/{oferta.pk}/").status_code == 404
    assert visitante.get(f"/oferta/{oferta.pk}/whatsapp/").status_code == 404
    assert titulos(visitante.get("/vendedor/doces-da-ana/")) == []

    # 8. Reativa com um clique e volta ao ar.
    vendedor.post(f"/meus-anuncios/{oferta.pk}/acao/", {"action": "resume"})
    assert titulos(visitante.get("/")) == ["Bolo de pote grande"]


# Fluxo 3 ---------------------------------------------------------------------


def hoje_na_vitrine(client) -> list[str]:
    return titulos(client.get("/", {"hoje": "1"}))


def test_fluxo_confirmacao_expira_no_horario_de_encerramento_e_a_virada_do_dia(
    seller_client, make_offer
):
    visitante = Client()
    categoria_id = categoria("comidas-e-doces").pk

    # A vendedora cria a oferta do dia já confirmada, encerrando às 14:00.
    with time_machine.travel("2026-11-05 09:00:00-03:00", tick=False):
        seller_client.post(
            "/meus-anuncios/novo/",
            {
                "kind": "daily",
                "title": "Bolo de pote",
                "category": categoria_id,
                "price": "8,50",
                "fulfillment": "Bloco 3",
                "closing_time": "14:00",
                "confirm_today": "on",
            },
        )
        assert hoje_na_vitrine(visitante) == ["Bolo de pote"]

    bolo = Offer.objects.get(title="Bolo de pote")
    # E outra, do dia, sem horário de encerramento, confirmada com um clique.
    cookies = make_offer(
        seller_client.seller,
        title="Cookies do dia",
        kind=Offer.Kind.DAILY,
        status=Offer.Status.ACTIVE,
    )
    assert cookies.daily_confirmed_on is None
    with time_machine.travel("2026-11-05 10:00:00-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == ["Bolo de pote"]  # sem confirmar não conta
        resposta = seller_client.post(
            f"/meus-anuncios/{cookies.pk}/acao/", {"action": "confirm_today"}, follow=True
        )
        assert parse_html(resposta).find("div", class_="aviso--success") is not None
        assert set(hoje_na_vitrine(visitante)) == {"Bolo de pote", "Cookies do dia"}

    # Horário de encerramento: vale até 13:59:59 e cai às 14:00:00 (o que vier primeiro).
    with time_machine.travel("2026-11-05 13:59:59-03:00", tick=False):
        assert set(hoje_na_vitrine(visitante)) == {"Bolo de pote", "Cookies do dia"}
    with time_machine.travel("2026-11-05 14:00:00-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == ["Cookies do dia"]
        # Continua no catálogo, mas sem indicação de disponibilidade imediata.
        home = visitante.get("/")
        assert "Bolo de pote" in titulos(home)
        cartao = parse_html(home).find("article", id=anchor_id(bolo.pk))
        assert "Disponível hoje" not in cartao.text
        pagina = parse_html(visitante.get(f"/oferta/{bolo.pk}/"))
        assert "Disponível hoje" not in pagina.find("main").text
        # Confirmar de novo depois do encerramento é recusado, com aviso, e nada muda.
        recusa = seller_client.post(
            f"/meus-anuncios/{bolo.pk}/acao/", {"action": "confirm_today"}, follow=True
        )
        assert parse_html(recusa).find("div", class_="aviso--error") is not None
        assert hoje_na_vitrine(visitante) == ["Cookies do dia"]

    # Sem horário de encerramento: vale até 23:58:59 e cai às 23:59:00. A virada do dia
    # em UTC (21:00 locais) não muda nada.
    with time_machine.travel("2026-11-05 21:30:00-03:00", tick=False):  # já é dia 6 em UTC
        assert hoje_na_vitrine(visitante) == ["Cookies do dia"]
    with time_machine.travel("2026-11-05 23:58:59-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == ["Cookies do dia"]
    with time_machine.travel("2026-11-05 23:59:00-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == []
        assert "Cookies do dia" in titulos(visitante.get("/"))  # segue no catálogo

    # Virada do dia: a confirmação de ontem não vale hoje.
    with time_machine.travel("2026-11-06 00:00:00-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == []
        vazio = visitante.get("/", {"hoje": "1"})
        assert "Ninguém confirmou oferta para hoje ainda" in vazio.content.decode()
        assert {"Bolo de pote", "Cookies do dia"} <= set(titulos(visitante.get("/")))

    # No dia seguinte, um clique reconfirma, e o horário de encerramento salvo continua valendo.
    with time_machine.travel("2026-11-06 08:00:00-03:00", tick=False):
        seller_client.post(f"/meus-anuncios/{bolo.pk}/acao/", {"action": "confirm_today"})
        assert hoje_na_vitrine(visitante) == ["Bolo de pote"]
    with time_machine.travel("2026-11-06 13:59:59-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == ["Bolo de pote"]
    with time_machine.travel("2026-11-06 14:00:00-03:00", tick=False):
        assert hoje_na_vitrine(visitante) == []


# Fluxo 4 ---------------------------------------------------------------------


def foto(offer, position=0) -> OfferPhoto:
    return OfferPhoto.objects.create(
        offer=offer,
        position=position,
        card_image=ContentFile(b"card", name="c.webp"),
        page_image=ContentFile(b"page", name="p.webp"),
        page_width=800,
        page_height=600,
    )


def retrato_do_banco() -> dict:
    return {
        "ofertas": list(Offer.objects.order_by("pk").values()),
        "variacoes": list(OfferVariant.objects.order_by("pk").values()),
        "fotos": list(OfferPhoto.objects.order_by("pk").values()),
        "vendedores": list(Seller.objects.order_by("pk").values()),
        "denuncias": list(Report.objects.order_by("pk").values()),
    }


def corpo_de_edicao(**extra) -> dict:
    return {
        "kind": "recurring",
        "title": "Invadido",
        "category": categoria("outros").pk,
        "price": "1,00",
        "fulfillment": "Em lugar nenhum",
    } | extra


def test_fluxo_vendedor_a_nao_mexe_em_anuncio_foto_nem_acao_de_b(
    seller_client, other_seller_client, make_offer
):
    a, b = seller_client, other_seller_client
    oferta_a = make_offer(a.seller, title="Oferta de A")
    oferta_b = make_offer(b.seller, title="Oferta de B", variants=[("Pequeno", 500)])
    foto_b = foto(oferta_b)
    nome_da_foto = foto_b.page_image.name
    antes = retrato_do_banco()

    # Ver o formulário de edição de B.
    assert a.get(f"/meus-anuncios/{oferta_b.pk}/editar/").status_code == 404

    # Editar B por POST direto, com e sem pedido para apagar a foto de B.
    for extra in (
        {},
        {"remove_photos": [foto_b.pk]},
        {"variant_name_0": "X", "variant_price_0": "1"},
    ):
        resposta = a.post(f"/meus-anuncios/{oferta_b.pk}/editar/", corpo_de_edicao(**extra))
        assert resposta.status_code == 404

    # Toda ação, valendo ou não para o estado, em B (e uma ação que nem existe).
    for acao in sorted(ACTIONS) + ["apagar"]:
        resposta = a.post(f"/meus-anuncios/{oferta_b.pk}/acao/", {"action": acao})
        assert resposta.status_code == 404, acao

    # Usar a própria oferta como ponte para apagar a foto de B não funciona.
    ponte = a.post(
        f"/meus-anuncios/{oferta_a.pk}/editar/", corpo_de_edicao(remove_photos=[foto_b.pk])
    )
    assert ponte.status_code != 302  # o formulário recusa o id que não é das fotos dela

    # Sem login, nada disso é possível.
    anonimo = Client()
    for caminho, dados in (
        (f"/meus-anuncios/{oferta_b.pk}/editar/", corpo_de_edicao()),
        (f"/meus-anuncios/{oferta_b.pk}/acao/", {"action": "pause"}),
    ):
        resposta = anonimo.post(caminho, dados)
        assert resposta.status_code == 302
        assert resposta["Location"].startswith("/entrar/")

    # O banco, as fotos e o armazenamento ficaram como estavam.
    depois = retrato_do_banco()
    depois["ofertas"] = [o for o in depois["ofertas"] if o["id"] != oferta_a.pk]
    antes["ofertas"] = [o for o in antes["ofertas"] if o["id"] != oferta_a.pk]
    assert depois == antes
    oferta_b.refresh_from_db()
    assert (oferta_b.title, oferta_b.status) == ("Oferta de B", "active")
    assert OfferPhoto.objects.filter(pk=foto_b.pk).exists()
    assert default_storage.exists(nome_da_foto)
    # A oferta de A também não foi tocada pelo pedido com a foto de B.
    oferta_a.refresh_from_db()
    assert oferta_a.title == "Oferta de A"

    # Controle: a dona consegue editar a própria oferta (o teste não é vazio).
    resposta = b.post(f"/meus-anuncios/{oferta_b.pk}/editar/", corpo_de_edicao(title="Nova de B"))
    assert resposta.status_code == 302
    oferta_b.refresh_from_db()
    assert oferta_b.title == "Nova de B"


# Fluxo 5 ---------------------------------------------------------------------


def test_fluxo_cadastro_com_erro_preserva_o_preenchimento_e_se_corrige_sem_recomecar(client):
    dados = {
        "display_name": "Doces da Ana",
        "email": "ana@exemplo.test",
        "password": PASSWORD,
        "whatsapp": "(35) 3821-1234",  # fixo: não vale
        "whatsapp_public": "on",
    }
    resposta = client.post("/cadastrar/", dados)
    assert resposta.status_code == 200
    assert not User.objects.exists()
    doc = parse_html(resposta)
    assert valor(doc, "display_name") == "Doces da Ana"
    assert valor(doc, "email") == "ana@exemplo.test"
    assert valor(doc, "whatsapp") == "(35) 3821-1234"
    assert doc.find("input", name="whatsapp_public").has("checked")
    assert not valor(doc, "password")
    assert PASSWORD not in resposta.content.decode()
    assert erro_do_campo(resposta, "whatsapp")
    assert doc.find("input", name="whatsapp").get("aria-invalid") == "true"

    # Só o campo errado muda; o resto vai exatamente como voltou.
    corrigido = dados | {"whatsapp": "(35) 91234-5678"}
    resposta = client.post("/cadastrar/", corrigido)
    assert resposta.status_code == 302
    assert Seller.objects.get().whatsapp_public is True


def test_fluxo_anuncio_com_erro_preserva_tudo_e_se_corrige_sem_recomecar(seller_client):
    comidas = categoria("comidas-e-doces")
    dados = {
        "kind": "daily",
        "title": "Bolo de pote",
        "category": comidas.pk,
        "price": "oito reais",  # inválido
        "description": "Feito hoje de manhã.\nSabores no cardápio.",
        "fulfillment": "Retirada no bloco 3",
        "closing_time": "14:00",
        "confirm_today": "on",
        "portion": "1 pote de 150 g",
        "ingredients": "Leite, ovos e farinha",
        "allergens": "Contém leite e ovos",
        "variant_name_0": "Ninho",
        "variant_price_0": "8,00",
        "variant_name_1": "Brigadeiro",
        "variant_price_1": "sete",  # inválido
    }
    resposta = seller_client.post("/meus-anuncios/novo/", dados)
    assert resposta.status_code == 200
    assert not Offer.objects.exists()
    doc = parse_html(resposta)

    # Tudo volta preenchido, inclusive o que depende do tipo e da categoria.
    marcado = [r.get("value") for r in doc.find_all("input", name="kind") if r.has("checked")]
    assert marcado == ["daily"]
    selecionada = [
        o.get("value")
        for o in doc.find("select", name="category").find_all("option")
        if o.has("selected")
    ]
    assert selecionada == [str(comidas.pk)]
    assert valor(doc, "title") == "Bolo de pote"
    assert valor(doc, "price") == "oito reais"
    assert (
        texto_da_area(doc, "description") == "Feito hoje de manhã. Sabores no cardápio."
    )  # `.text` junta linhas
    assert "Feito hoje de manhã.\nSabores no cardápio." in resposta.content.decode().replace(
        "\r\n", "\n"
    )
    assert valor(doc, "fulfillment") == "Retirada no bloco 3"
    assert valor(doc, "closing_time") == "14:00"
    assert doc.find("input", name="confirm_today").has("checked")
    assert valor(doc, "portion") == "1 pote de 150 g"
    assert texto_da_area(doc, "ingredients") == "Leite, ovos e farinha"
    assert texto_da_area(doc, "allergens") == "Contém leite e ovos"
    assert (valor(doc, "variant_name_0"), valor(doc, "variant_price_0")) == ("Ninho", "8,00")
    assert (valor(doc, "variant_name_1"), valor(doc, "variant_price_1")) == ("Brigadeiro", "sete")

    # Cada erro aparece junto do campo dele.
    assert erro_do_campo(resposta, "price")
    assert erro_do_campo(resposta, "variant_price_1")
    assert not erro_do_campo(resposta, "title")
    assert doc.find("input", name="price").get("aria-invalid") == "true"
    assert doc.find(role="alert") is not None  # resumo no topo

    # Corrige os dois campos e reenvia o mesmo formulário.
    corrigido = dados | {"price": "8,00", "variant_price_1": "7,00"}
    resposta = seller_client.post("/meus-anuncios/novo/", corrigido)
    assert resposta.status_code == 302
    oferta = Offer.objects.get()
    assert (oferta.title, oferta.price_cents, oferta.closing_time) == (
        "Bolo de pote",
        800,
        time(14, 0),
    )
    assert oferta.ingredients == "Leite, ovos e farinha"
    assert list(oferta.variants.values_list("name", "price_cents")) == [
        ("Ninho", 800),
        ("Brigadeiro", 700),
    ]


def test_fluxo_denuncia_com_erro_preserva_o_texto_e_se_corrige(client, make_offer):
    oferta = make_offer(title="Bolo de pote")
    url = f"/oferta/{oferta.pk}/denunciar/"

    # Sem escolher o motivo: o texto digitado volta.
    resposta = client.post(url, {"details": "Pediu pix adiantado e sumiu."})
    assert resposta.status_code == 200
    assert not Report.objects.exists()
    doc = parse_html(resposta)
    assert texto_da_area(doc, "details") == "Pediu pix adiantado e sumiu."
    assert erro_do_campo(resposta, "reason")

    # Motivo escolhido, texto longo demais: o motivo e o texto voltam.
    longo = "a" * 501
    resposta = client.post(url, {"reason": "misleading", "details": longo})
    assert resposta.status_code == 200
    assert not Report.objects.exists()
    doc = parse_html(resposta)
    marcado = [r.get("value") for r in doc.find_all("input", name="reason") if r.has("checked")]
    assert marcado == ["misleading"]
    assert texto_da_area(doc, "details") == longo
    assert erro_do_campo(resposta, "details")

    resposta = client.post(url, {"reason": "misleading", "details": "Pediu pix adiantado."})
    assert resposta.status_code == 302
    assert Report.objects.get().details == "Pediu pix adiantado."


def test_fluxo_perfil_com_erro_preserva_tudo_e_nada_e_gravado(seller_client):
    seller = seller_client.seller
    antes = Seller.objects.filter(pk=seller.pk).values().get()
    dados = {
        "display_name": "Nome Novo",
        "bio": "Bolos e doces feitos no dia.",
        "service_area": "Campus e centro",
        "hours": "Seg a sex, 12h às 14h",
        "whatsapp": "(10) 91234-5678",  # DDD que não existe
        "whatsapp_public": "nao",
    }
    resposta = seller_client.post("/perfil/", dados)
    assert resposta.status_code == 200
    doc = parse_html(resposta)
    assert valor(doc, "display_name") == "Nome Novo"
    assert texto_da_area(doc, "bio") == "Bolos e doces feitos no dia."
    assert valor(doc, "service_area") == "Campus e centro"
    assert valor(doc, "hours") == "Seg a sex, 12h às 14h"
    assert valor(doc, "whatsapp") == "(10) 91234-5678"
    marcado = [
        r.get("value") for r in doc.find_all("input", name="whatsapp_public") if r.has("checked")
    ]
    assert marcado == ["nao"]
    assert erro_do_campo(resposta, "whatsapp")
    assert Seller.objects.filter(pk=seller.pk).values().get() == antes

    resposta = seller_client.post("/perfil/", dados | {"whatsapp": "(35) 98888-7777"}, follow=True)
    assert parse_html(resposta).find("div", class_="aviso--success") is not None
    seller.refresh_from_db()
    assert (seller.display_name, seller.whatsapp_number, seller.whatsapp_public) == (
        "Nome Novo",
        "5535988887777",
        False,
    )


# Fluxo 6 ---------------------------------------------------------------------

FOCAVEIS = {"a", "button", "input", "select", "textarea", "summary"}


def focaveis(doc) -> list:
    """Elementos que recebem foco pelo Tab, na ordem do DOM."""
    itens = []
    for el in doc.iter():
        if any(a.tag == "template" for a in el.ancestors()):
            continue
        if el.has("disabled") or el.get("hidden") is not None:
            continue
        tabindex = el.get("tabindex")
        if tabindex is not None and tabindex.lstrip("-").isdigit() and int(tabindex) < 0:
            continue
        if el.tag == "a" and el.has("href") or el.tag in FOCAVEIS - {"a"}:
            if el.tag == "input" and (el.get("type") or "").lower() == "hidden":
                continue
            itens.append(el)
        elif tabindex is not None and tabindex.lstrip("-").isdigit():
            itens.append(el)
    return itens


@pytest.fixture
def mundo(make_seller, make_offer, make_user):
    vendedora = make_seller(display_name="Doces da Ana")
    oferta = make_offer(vendedora, title="Bolo de pote", variants=[("Ninho", 800), ("Mel", 700)])
    pendente = make_offer(
        make_seller(display_name="Novo", trusted=False),
        title="Pendente",
        approval=Offer.Approval.PENDING,
    )
    return {"vendedora": vendedora, "oferta": oferta, "pendente": pendente}


def paginas(mundo, seller_client, staff_client):
    oferta, vendedora = mundo["oferta"], mundo["vendedora"]
    publicas = [
        (Client(), "/"),
        (Client(), "/?q=bolo&cat=comidas-e-doces&hoje=1"),
        (Client(), "/?q=nadaaqui"),
        (Client(), f"/oferta/{oferta.pk}/"),
        (Client(), f"/oferta/{oferta.pk}/denunciar/"),
        (Client(), f"/vendedor/{vendedora.slug}/"),
        (Client(), "/entrar/"),
        (Client(), "/cadastrar/"),
        (Client(), "/privacidade/"),
    ]
    vendedor = [
        (seller_client, "/meus-anuncios/"),
        (seller_client, "/meus-anuncios/novo/"),
        (seller_client, "/perfil/"),
        (seller_client, "/perfil/excluir-conta/"),
    ]
    admin = [(staff_client, "/admin/"), (staff_client, "/admin/denuncias/")]
    return publicas + vendedor + admin


def test_fluxo_teclado_pular_para_o_conteudo_e_primeiro_foco_em_todas_as_telas(
    mundo, seller_client, staff_client
):
    for cliente, url in paginas(mundo, seller_client, staff_client):
        resposta = cliente.get(url)
        assert resposta.status_code == 200, url
        doc = parse_html(resposta)
        ordem = focaveis(doc)
        primeiro = ordem[0]
        # O primeiro Tab cai no link "Pular para o conteúdo", que aponta para o <main>.
        assert primeiro.tag == "a", url
        assert primeiro.get("href") == "#conteudo", url
        assert "Pular para o conteúdo" in primeiro.text, url
        mains = doc.find_all("main")
        assert [m.get("id") for m in mains] == ["conteudo"], url
        # O destino do pulo vem depois do cabeçalho e antes do rodapé.
        elementos = list(doc.iter())
        assert elementos.index(mains[0]) > elementos.index(primeiro), url


def test_fluxo_teclado_nada_de_tabindex_positivo_nem_foco_preso(mundo, seller_client, staff_client):
    for cliente, url in paginas(mundo, seller_client, staff_client):
        doc = parse_html(cliente.get(url))
        for el in doc.iter():
            tabindex = el.get("tabindex")
            if tabindex is None:
                continue
            assert int(tabindex) <= 0, f"{url}: <{el.tag} tabindex={tabindex}> distorce a ordem"
        # Controle é de verdade (link ou botão), não um div com clique.
        for el in doc.iter():
            assert not any(a.startswith("on") for a in el.attrs), f"{url}: <{el.tag}> com on*"
            if el.tag in {"div", "span"} and el.get("role") in {"button", "link"}:
                raise AssertionError(f"{url}: <{el.tag} role={el.get('role')}> no lugar de botão")


def test_fluxo_teclado_ordem_de_foco_da_pagina_inicial_e_logica(mundo):
    doc = parse_html(Client().get("/"))
    ordem = focaveis(doc)

    def posicao(predicado) -> int:
        return next(i for i, el in enumerate(ordem) if predicado(el))

    pular = posicao(lambda e: e.get("href") == "#conteudo")
    marca = posicao(lambda e: e.tag == "a" and e.get("class") and "marca" in e.get("class").split())
    busca = posicao(lambda e: e.tag == "input" and e.get("name") == "q")
    botao_buscar = posicao(lambda e: e.tag == "button" and e.get("type") == "submit")
    chip_tudo = posicao(lambda e: e.tag == "a" and "chip" in (e.get("class") or "").split())
    chip_hoje = posicao(lambda e: "chip--hoje" in (e.get("class") or "").split())
    cartao = posicao(lambda e: e.tag == "a" and "cartao-oferta__link" in (e.get("class") or ""))
    privacidade = posicao(lambda e: e.get("href") == "/privacidade/")
    assert pular < marca < busca < botao_buscar < chip_tudo < chip_hoje < cartao < privacidade, (
        "ordem de foco: pular, marca, busca, botão, categorias, hoje, ofertas, rodapé"
    )
    # Um cartão de oferta tem um único ponto de foco (CA3): nenhum botão concorrente.
    for article in doc.find_all("article"):
        assert len([e for e in focaveis(article)]) == 1


def test_fluxo_teclado_formularios_seguem_a_ordem_visual_dos_campos(mundo, seller_client):
    doc = parse_html(seller_client.get("/meus-anuncios/novo/"))
    form = doc.find("form", class_="form-oferta")
    nomes = [e.get("name") for e in focaveis(form) if e.get("name")]
    unicos = list(dict.fromkeys(nomes))
    assert "csrfmiddlewaretoken" not in unicos  # campo hidden nunca entra no Tab
    ordem_relativa = ["kind", "title", "category", "price", "description", "fulfillment", "photos"]
    assert [n for n in unicos if n in ordem_relativa] == ordem_relativa
    # O botão de enviar é o último foco do formulário.
    assert focaveis(form)[-1].tag in {"button", "a"}
    assert focaveis(form)[-1].get("type") in {"submit", None}


def test_fluxo_celular_viewport_sem_travar_o_zoom_em_todas_as_telas(
    mundo, seller_client, staff_client
):
    for cliente, url in paginas(mundo, seller_client, staff_client):
        doc = parse_html(cliente.get(url))
        metas = [m for m in doc.find_all("meta") if m.get("name") == "viewport"]
        assert len(metas) == 1, url
        conteudo = metas[0].get("content").replace(" ", "").lower()
        assert "width=device-width" in conteudo, url
        assert "initial-scale=1" in conteudo, url
        # Quem precisa de zoom de 200% não pode ser impedido de dar zoom.
        assert "user-scalable=no" not in conteudo, url
        assert "user-scalable=0" not in conteudo, url
        assert "maximum-scale" not in conteudo, url


def regras_css(css: str) -> list[tuple[list[str], str]]:
    """(seletores, corpo) de cada regra, inclusive as de dentro de `@media`/`@supports`.

    Divide por "}": em cada pedaço, o corpo é o que vem depois do último "{" e o
    seletor é o trecho entre o "{" ou ";" anterior e esse "{". Não depende da ordem
    nem da vizinhança das regras.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    regras = []
    for pedaco in css.split("}"):
        if "{" not in pedaco:
            continue
        cabeca, corpo = pedaco.rsplit("{", 1)
        seletor = re.split(r"[{;]", cabeca)[-1]
        regras.append(([s.strip() for s in seletor.split(",")], corpo))
    return regras


def regra_css(css: str, seletor: str) -> list[str]:
    """Corpos de todas as regras cujo seletor (lista separada por vírgula) contém `seletor`."""
    corpos = [corpo for seletores, corpo in regras_css(css) if seletor in seletores]
    assert corpos, f"seletor {seletor!r} não encontrado em app.css"
    return corpos


def alturas_minimas_px(css: str, corpos: list[str]) -> list[float]:
    """Cada `min-height` declarado nos corpos, em px (resolve `var(--x)` pelo `:root`)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    alturas = []
    for corpo in corpos:
        for valor in re.findall(r"min-height:\s*([^;]+?)\s*(?:;|$)", corpo.strip()):
            texto = valor.strip()
            variavel = re.fullmatch(r"var\((--[\w-]+)\)", texto)
            if variavel:
                definicao = re.search(rf"{variavel.group(1)}:\s*([^;]+);", css)
                assert definicao, texto
                texto = definicao.group(1).strip()
            numero = re.match(r"([\d.]+)(rem|px)", texto)
            assert numero, texto
            alturas.append(float(numero.group(1)) * (16 if numero.group(2) == "rem" else 1))
    assert alturas, f"sem min-height em: {corpos!r}"[:200]
    return alturas


def test_regras_css_acha_a_regra_qualquer_que_seja_a_vizinhanca():
    """O parser não pode depender do que vem antes da regra."""
    css = (
        ":root { --toque: 2.75rem; }\n"
        "@import url(x.css);\n.a { color: red; }\n.b { color: blue; }\n"
        "@media (hover: hover) { .a:hover { color: red; } .c { x: y; } }\n"
        ".botao { min-height: var(--toque); }\n"
        "@media (min-width: 60em) { .botao, .chip { min-height: 40px; } }\n"
    )
    assert alturas_minimas_px(css, regra_css(css, ".botao")) == [44.0, 40.0]
    assert regra_css(css, ".c") == [" x: y; "]


def test_fluxo_celular_alvos_de_toque_de_pelo_menos_44px_no_css():
    """Só prova que o CSS declara 44 px; a medida real vai para o roteiro manual."""
    from pathlib import Path

    css = (Path(__file__).resolve().parents[3] / "static/css/app.css").read_text()
    for seletor in (".botao", ".chip", ".marca", ".cabecalho__nav a", ".voltar", ".pular"):
        # Todo `min-height` declarado para o seletor (inclusive em @media) é de 44 px ou mais.
        assert min(alturas_minimas_px(css, regra_css(css, seletor))) >= 44, seletor
    # Campos de formulário: 48 px.
    assert re.search(r"--campo-altura:\s*3rem", css)


def test_fluxo_celular_nada_depende_de_javascript(mundo, seller_client, staff_client):
    """Nenhuma tela exige JS para o fluxo: formulários e filtros são GET/POST e links."""
    for cliente, url in paginas(mundo, seller_client, staff_client):
        doc = parse_html(cliente.get(url))
        for form in doc.find_all("form"):
            assert (form.get("method") or "get").lower() in {"get", "post"}, url
            assert form.get("action") is not None or form.get("role") == "search", url
            enviar = [
                b for b in form.find_all("button") if (b.get("type") or "submit") == "submit"
            ] + [i for i in form.find_all("input") if i.get("type") == "submit"]
            assert enviar, f"{url}: formulário sem botão de enviar"
        # Os filtros da lista são links comuns.
        for chip in doc.find_all("a", class_="chip"):
            assert chip.get("href", "").startswith("/"), url
