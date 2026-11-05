"""Casos de borda e regressões do MVP, pela porta da frente (`Client`).

Complementa os testes por área: aqui entram as combinações que a pessoa real
produz (preço em formatos diferentes, busca com acento, URL adulterada, WhatsApp
revogado no meio do caminho, conta apagada com anúncio em todo estado).
"""

import unicodedata
from datetime import date, time, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import time_machine
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, Offer, OfferPhoto, Seller
from apps.catalog.presenters import anchor_id
from apps.core.testing import assert_phone_absent, make_image_bytes, parse_html
from apps.metrics.models import DailyOfferStat, DailySearchMiss
from apps.moderation.models import Report
from conftest import DEFAULT_WHATSAPP
from texts import seller as seller_texts

pytestmark = pytest.mark.django_db

BROWSER = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"}
AGORA = "2026-11-05 12:00:00-03:00"
HOJE = date(2026, 11, 5)
NEW_URL = "/meus-anuncios/novo/"


@pytest.fixture(autouse=True)
def relogio():
    with time_machine.travel(AGORA, tick=False):
        yield


def titulos(response) -> list[str]:
    return [h.text for h in parse_html(response).find_all("h3", class_="cartao-oferta__titulo")]


def erro_do_campo(response, name: str) -> str:
    el = parse_html(response).find(id=f"id_{name}_error")
    return el.text if el is not None else ""


def corpo_do_anuncio(**extra) -> dict:
    return {
        "kind": "recurring",
        "title": "Bolo de pote",
        "category": Category.objects.get(slug="comidas-e-doces").pk,
        "price": "8,50",
        "fulfillment": "Retirada no bloco 3",
    } | extra


def foto(offer, position=0) -> OfferPhoto:
    return OfferPhoto.objects.create(
        offer=offer,
        position=position,
        card_image=ContentFile(b"card", name="c.webp"),
        page_image=ContentFile(b"page", name="p.webp"),
        page_width=800,
        page_height=600,
    )


# Preço -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("digitado", "centavos", "exibido"),
    [
        ("0", 0, "R$ 0,00"),
        ("1.250,50", 125050, "R$ 1.250,50"),
        ("1250,5", 125050, "R$ 1.250,50"),
        ("R$ 8,50", 850, "R$ 8,50"),
        ("8,", 800, "R$ 8,00"),
        ("8.5", 850, "R$ 8,50"),
        ("100000", 10_000_000, "R$ 100.000,00"),  # o teto
    ],
)
def test_preco_em_varios_formatos_e_gravado_em_centavos_e_exibido_em_real(
    seller_client, client, digitado, centavos, exibido
):
    resposta = seller_client.post(NEW_URL, corpo_do_anuncio(price=digitado))
    assert resposta.status_code == 302
    oferta = Offer.objects.get()
    assert oferta.price_cents == centavos
    assert exibido in client.get("/").content.decode()
    assert exibido in client.get(f"/oferta/{oferta.pk}/").content.decode()


@pytest.mark.parametrize(
    "digitado",
    ["-5", "-0,50", "R$ -3", "1,250.50", "1,5,0", "0,001", ",50", "abc", "1e3", "  ", "100000,01"],
)
def test_preco_invalido_ou_negativo_e_recusado_junto_do_campo(seller_client, digitado):
    resposta = seller_client.post(NEW_URL, corpo_do_anuncio(price=digitado))
    assert resposta.status_code == 200
    assert not Offer.objects.exists()
    assert erro_do_campo(resposta, "price")


def test_preco_negativo_numa_variacao_e_recusado(seller_client):
    resposta = seller_client.post(
        NEW_URL, corpo_do_anuncio(variant_name_0="Ninho", variant_price_0="-1")
    )
    assert resposta.status_code == 200
    assert not Offer.objects.exists()
    assert erro_do_campo(resposta, "variant_price_0")


def test_preco_zero_com_variacoes_mostra_a_partir_de_zero(client, make_offer):
    make_offer(title="Brinde", price_cents=0, variants=[("Pequeno", 0), ("Grande", 500)])
    html = client.get("/").content.decode()
    assert "A partir de" in html and "R$ 0,00" in html


# Busca -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "consulta",
    ["pao", "PÃO", "pão", "Pão De Queijo", "pa\u0303o", "  pao   queijo ", "queijo pao"],
)
def test_busca_acha_titulo_com_acento_em_qualquer_forma_de_digitar(client, make_offer, consulta):
    make_offer(title="Pão de queijo")
    make_offer(title="Brigadeiro")
    assert titulos(client.get("/", {"q": consulta})) == ["Pão de queijo"]


def test_busca_com_titulo_gravado_decomposto_acha_com_busca_normal(client, make_offer):
    titulo = unicodedata.normalize("NFD", "Açaí na tigela")
    make_offer(title=titulo)
    for consulta in ("acai", "AÇAÍ", titulo):
        assert titulos(client.get("/", {"q": consulta})) == [titulo]


def test_busca_por_vendedor_com_acento(client, make_seller, make_offer):
    make_offer(make_seller(display_name="José Doces"), title="Cookie")
    assert titulos(client.get("/", {"q": "jose"})) == ["Cookie"]


@pytest.mark.parametrize("consulta", ["%%", "__", "\\\\", "' OR 1=1 --"])
def test_busca_com_curinga_ou_lixo_nao_casa_tudo_nem_quebra(client, make_offer, consulta):
    make_offer(title="Bolo de pote")
    resposta = client.get("/", {"q": consulta}, headers=BROWSER)
    assert resposta.status_code == 200
    assert titulos(resposta) == []


def test_busca_com_caractere_nul_nao_derruba_a_pagina_nem_grava_nul(client, make_offer):
    make_offer(title="Bolo de pote")
    resposta = client.get("/", {"q": "a\x00b"}, headers=BROWSER)
    assert resposta.status_code == 200
    assert not any(
        "\x00" in termo for termo in DailySearchMiss.objects.values_list("term", flat=True)
    )


def test_busca_sem_resultado_escapa_o_termo_e_registra_normalizado(client, make_offer):
    make_offer(title="Bolo de pote")
    resposta = client.get("/", {"q": "<script>alert(1)</script>"}, headers=BROWSER)
    html = resposta.content.decode()
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html
    assert DailySearchMiss.objects.get().term == "<script>alert(1)</script>"


def test_busca_muito_longa_e_cortada_sem_erro(client, make_offer):
    make_offer(title="Bolo de pote")
    resposta = client.get("/", {"q": "bolo " * 2000}, headers=BROWSER)
    assert resposta.status_code == 200


# Paginação e filtros na URL ---------------------------------------------------


@pytest.fixture
def vinte_e_cinco(make_offer, make_seller):
    vendedor = make_seller()
    return [make_offer(vendedor, title=f"Oferta {i:02d}") for i in range(25)]


def test_pagina_999_mostra_tudo_sem_erro_e_sem_ver_mais(client, vinte_e_cinco):
    resposta = client.get("/", {"pagina": "999"})
    assert resposta.status_code == 200
    assert len(titulos(resposta)) == 25
    assert "Mostrar mais ofertas" not in resposta.content.decode()


@pytest.mark.parametrize("pagina", ["abc", "-1", "0", "1.5", "1e3", "٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣", "9" * 5000])
def test_pagina_invalida_volta_para_a_primeira(client, vinte_e_cinco, pagina):
    resposta = client.get("/", {"pagina": pagina})
    assert resposta.status_code == 200
    quantidade = len(titulos(resposta))
    assert quantidade in {20, 25}
    if quantidade == 20:
        assert "Mostrar mais ofertas" in resposta.content.decode()


def test_pagina_2_traz_o_resto_e_o_ver_mais_leva_a_ancora_da_primeira_nova(client, vinte_e_cinco):
    primeira = client.get("/")
    assert len(titulos(primeira)) == 20
    mais = next(a for a in parse_html(primeira).find_all("a") if a.text == "Mostrar mais ofertas")
    link = urlsplit(mais.get("href"))
    assert parse_qs(link.query)["pagina"] == ["2"]
    segunda = client.get(mais.get("href"))
    assert len(titulos(segunda)) == 25
    assert link.fragment.startswith("oferta-")
    assert parse_html(segunda).find("article", id=link.fragment) is not None


@pytest.mark.parametrize(
    "cat", ["", "inexistente", "Comidas e doces", "comidas-e-doces%00", "' OR 1=1", "a" * 300, "é"]
)
def test_categoria_inexistente_ou_estranha_e_ignorada(client, make_offer, cat):
    make_offer(title="Bolo de pote")
    resposta = client.get("/", {"cat": cat})
    assert resposta.status_code == 200
    assert titulos(resposta) == ["Bolo de pote"]
    atuais = [a.text for a in parse_html(resposta).find_all("a") if a.get("aria-current")]
    assert "Comidas e doces" not in atuais


def test_hoje_diferente_de_1_nao_filtra(client, make_offer):
    make_offer(title="Bolo de pote")
    for valor in ("0", "true", "sim", ""):
        assert titulos(client.get("/", {"hoje": valor})) == ["Bolo de pote"]


def test_pagina_da_oferta_ignora_parametros_de_lista_estranhos(client, make_offer):
    oferta = make_offer()
    resposta = client.get(
        f"/oferta/{oferta.pk}/", {"q": "x" * 500, "cat": "<b>", "pagina": "abc", "hoje": "1"}
    )
    assert resposta.status_code == 200
    voltar = parse_html(resposta).find("a", class_="voltar").get("href")
    assert voltar.startswith("/") and "<b>" not in voltar
    assert voltar.endswith(f"#{anchor_id(oferta.pk)}")


# XSS: texto de gente nunca vira HTML -------------------------------------------


def test_titulo_e_nome_com_html_aparecem_escapados_em_todas_as_telas(
    client, make_seller, make_offer, staff_client
):
    perigo = "<img src=x onerror=alert(1)>\"'"
    vendedora = make_seller(display_name="Ana <b>negrito</b>", bio=perigo, service_area=perigo)
    oferta = make_offer(
        vendedora,
        title="Bolo <script>alert(1)</script>",
        description=perigo,
        fulfillment=perigo,
        approval=Offer.Approval.APPROVED,
    )
    dono = Client()
    dono.force_login(vendedora.user)
    for cliente, url in (
        (client, "/"),
        (client, f"/oferta/{oferta.pk}/"),
        (client, f"/vendedor/{vendedora.slug}/"),
        (client, f"/oferta/{oferta.pk}/denunciar/"),
        (dono, "/meus-anuncios/"),
        (dono, f"/meus-anuncios/{oferta.pk}/editar/"),
        (dono, "/perfil/"),
        (staff_client, "/admin/anuncios/"),
        (staff_client, f"/admin/anuncios/{oferta.pk}/"),
    ):
        html = cliente.get(url).content.decode()
        assert "<script>alert(1)" not in html, url
        assert "<img src=x" not in html, url
        assert "<b>negrito" not in html, url


# Oferta do dia e venda pontual ---------------------------------------------------


def test_oferta_do_dia_confirmada_com_encerramento_ja_passado_nao_aparece_como_hoje(
    client, seller_client, make_offer
):
    bolo = make_offer(
        seller_client.seller,
        title="Bolo de pote",
        kind=Offer.Kind.DAILY,
        daily_confirmed_on=HOJE,
        closing_time=time(9, 0),  # são 12:00
    )
    assert titulos(client.get("/", {"hoje": "1"})) == []
    assert titulos(client.get("/")) == ["Bolo de pote"]
    assert "Disponível hoje" not in client.get(f"/oferta/{bolo.pk}/").content.decode()
    # O anúncio segue ativo e contatável: só perdeu a indicação de disponibilidade imediata.
    assert client.get(f"/oferta/{bolo.pk}/whatsapp/").status_code == 302


def test_painel_com_encerramento_ja_passado_recusa_confirmar_e_explica(seller_client, make_offer):
    bolo = make_offer(
        seller_client.seller,
        kind=Offer.Kind.DAILY,
        daily_confirmed_on=HOJE - timedelta(days=1),
        closing_time=time(9, 0),
    )
    resposta = seller_client.post(
        f"/meus-anuncios/{bolo.pk}/acao/", {"action": "confirm_today"}, follow=True
    )
    aviso = parse_html(resposta).find("div", class_="aviso--error")
    assert aviso is not None and seller_texts.ACTION_CLOSING_PASSED in aviso.text
    bolo.refresh_from_db()
    assert bolo.daily_confirmed_on == HOJE - timedelta(days=1)


def test_venda_pontual_com_14_dias_exatos_sai_da_lista_e_volta_com_um_clique(
    client, seller_client, make_offer
):
    agora = timezone.now()
    pontual = make_offer(
        seller_client.seller,
        title="Patinete",
        kind=Offer.Kind.ONE_OFF,
        last_confirmed_at=agora - timedelta(days=14, seconds=-1),
    )
    # 13 dias, 23h59min59s: ainda aparece.
    assert titulos(client.get("/")) == ["Patinete"]
    assert client.get(f"/oferta/{pontual.pk}/").status_code == 200

    # 14 dias exatos: sai da lista, da página e do contato; o vendedor vê "Precisa de confirmação".
    Offer.objects.filter(pk=pontual.pk).update(last_confirmed_at=agora - timedelta(days=14))
    assert titulos(client.get("/")) == []
    assert client.get(f"/oferta/{pontual.pk}/").status_code == 404
    assert client.get(f"/oferta/{pontual.pk}/whatsapp/").status_code == 404
    assert titulos(client.get(f"/vendedor/{seller_client.seller.slug}/")) == []
    painel = parse_html(seller_client.get("/meus-anuncios/"))
    cartao = painel.find("article", id=f"anuncio-{pontual.pk}")
    assert "Precisa de confirmação" in cartao.text
    botoes = {b.get("value") for b in cartao.find_all("button", name="action")}
    assert "reconfirm" in botoes

    # Um clique reativa.
    resposta = seller_client.post(
        f"/meus-anuncios/{pontual.pk}/acao/", {"action": "reconfirm"}, follow=True
    )
    assert parse_html(resposta).find("div", class_="aviso--success") is not None
    assert titulos(client.get("/")) == ["Patinete"]


# WhatsApp revogado no meio do fluxo -------------------------------------------------


def test_revogar_o_whatsapp_depois_que_o_visitante_abriu_a_oferta_derruba_o_contato(
    client, make_seller, make_offer
):
    vendedora = make_seller(whatsapp_public=True)
    oferta = make_offer(vendedora, title="Bolo de pote", variants=[("Ninho", 800)])
    dono = Client()
    dono.force_login(vendedora.user)

    # O visitante já está na página, com o formulário carregado.
    pagina = client.get(f"/oferta/{oferta.pk}/", headers=BROWSER)
    form = parse_html(pagina).find("form", action=f"/oferta/{oferta.pk}/whatsapp/")
    assert form is not None
    assert_phone_absent(pagina, DEFAULT_WHATSAPP)

    # A vendedora revoga a autorização.
    resposta = dono.post(
        "/perfil/",
        {
            "display_name": vendedora.display_name,
            "whatsapp": "(35) 91234-5678",
            "whatsapp_public": "nao",
        },
    )
    assert resposta.status_code == 302

    # O envio do formulário que já estava aberto não leva a lugar nenhum.
    envio = client.get(form.get("action"), headers=BROWSER)
    assert envio.status_code == 404
    assert "Location" not in envio.headers
    assert_phone_absent(envio, DEFAULT_WHATSAPP)
    assert not DailyOfferStat.objects.filter(offer=oferta, whatsapp_clicks__gt=0).exists()
    # E tudo mais some: lista, página, vendedora.
    assert titulos(client.get("/")) == []
    assert client.get(f"/oferta/{oferta.pk}/").status_code == 404
    assert client.get(f"/vendedor/{vendedora.slug}/").status_code == 404
    # Ela mesma ainda vê o anúncio no painel, com o aviso de que o contato não está liberado.
    painel = dono.get("/meus-anuncios/")
    assert "Bolo de pote" in painel.content.decode()
    assert parse_html(painel).find("div", class_="aviso--warning") is not None

    # Dá a autorização de novo: volta na hora.
    dono.post(
        "/perfil/",
        {
            "display_name": vendedora.display_name,
            "whatsapp": "(35) 91234-5678",
            "whatsapp_public": "sim",
        },
    )
    assert client.get(f"/oferta/{oferta.pk}/whatsapp/").status_code == 302


# Exclusão de conta com anúncios em todos os estados ------------------------------------


def test_excluir_conta_tira_do_ar_anuncios_em_todos_os_estados_e_apaga_as_fotos(
    client, make_user, make_seller, make_offer, django_capture_on_commit_callbacks
):
    senha = "senha-da-conta-123"
    usuario = make_user(email="ana@exemplo.test", password=senha)
    vendedora = make_seller(user=usuario)
    agora = timezone.now()
    estados = {
        "recorrente ativo": {},
        "recorrente pausado": {"status": Offer.Status.PAUSED},
        "recorrente esgotado": {"status": Offer.Status.SOLD_OUT},
        "do dia confirmado": {"kind": Offer.Kind.DAILY, "daily_confirmed_on": HOJE},
        "pontual vendido": {"kind": Offer.Kind.ONE_OFF, "status": Offer.Status.SOLD},
        "pontual vencido": {
            "kind": Offer.Kind.ONE_OFF,
            "last_confirmed_at": agora - timedelta(days=20),
        },
        "aguardando aprovação": {"approval": Offer.Approval.PENDING},
        "oculto": {"hidden_at": agora, "hidden_reason": "teste"},
    }
    ofertas = {}
    for nome, campos in estados.items():
        oferta = make_offer(vendedora, title=nome, variants=[("A", 100)], **campos)
        foto(oferta)
        Report.objects.create(offer=oferta, reason=Report.Reason.OTHER, details="x")
        DailyOfferStat.objects.create(date=HOJE, offer=oferta, views=2, whatsapp_clicks=1)
        ofertas[nome] = oferta
    de_outra = make_offer(title="Oferta de outra pessoa")
    foto(de_outra)
    nomes_de_arquivo = [p.page_image.name for p in OfferPhoto.objects.exclude(offer=de_outra)]
    assert nomes_de_arquivo and all(default_storage.exists(n) for n in nomes_de_arquivo)

    # Antes: o público vê as que estão no ar.
    assert "recorrente ativo" in titulos(client.get("/"))

    dono = Client()
    dono.force_login(usuario)
    with django_capture_on_commit_callbacks(execute=True):
        resposta = dono.post("/perfil/excluir-conta/", {"password": senha})
    assert resposta.status_code == 302

    # Na hora: nada dela aparece em lugar nenhum e nada responde.
    assert titulos(client.get("/")) == ["Oferta de outra pessoa"]
    assert client.get(f"/vendedor/{vendedora.slug}/").status_code == 404
    for nome, oferta in ofertas.items():
        assert client.get(f"/oferta/{oferta.pk}/").status_code == 404, nome
        assert client.get(f"/oferta/{oferta.pk}/whatsapp/").status_code == 404, nome
        assert client.get(f"/oferta/{oferta.pk}/denunciar/").status_code == 404, nome

    # No banco e no armazenamento.
    assert not User.objects.filter(email="ana@exemplo.test").exists()
    assert not Seller.objects.filter(pk=vendedora.pk).exists()
    assert Offer.objects.count() == 1
    assert OfferPhoto.objects.count() == 1
    assert Report.objects.count() == 0
    assert DailyOfferStat.objects.count() == 0
    assert not any(default_storage.exists(n) for n in nomes_de_arquivo)
    assert default_storage.exists(de_outra.photos.get().page_image.name)


# Denúncia ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campos",
    [
        {"hidden_at": timezone.now()},
        {"approval": Offer.Approval.PENDING},
        {"status": Offer.Status.PAUSED},
    ],
    ids=["oculta", "aguardando aprovação", "pausada"],
)
def test_denunciar_oferta_fora_do_ar_da_404_e_nao_grava(client, make_offer, campos):
    oferta = make_offer(**campos)
    url = f"/oferta/{oferta.pk}/denunciar/"
    assert client.get(url).status_code == 404
    resposta = client.post(url, {"reason": "misleading", "details": "x"})
    assert resposta.status_code == 404
    assert not Report.objects.exists()


def test_denuncia_de_oferta_que_foi_ocultada_depois_continua_na_fila_do_admin(
    client, staff_client, make_offer
):
    oferta = make_offer(title="Bolo de pote")
    client.post(f"/oferta/{oferta.pk}/denunciar/", {"reason": "misleading"})
    staff_client.post(f"/admin/anuncios/{oferta.pk}/ocultar/", {"reason": "golpe"})
    assert client.get(f"/oferta/{oferta.pk}/").status_code == 404
    fila = staff_client.get("/admin/denuncias/")
    assert "Bolo de pote" in fila.content.decode()


# ?variacao= ---------------------------------------------------------------------------


@pytest.mark.parametrize("bruto", ["", "abc", "-1", "0", "1.5", "1e3", " ", "9" * 5000, "a\x00b"])
def test_variacao_estranha_cai_na_mensagem_so_com_o_nome(client, make_offer, bruto):
    oferta = make_offer(title="Bolo de pote", variants=[("Ninho", 800)])
    resposta = client.get(f"/oferta/{oferta.pk}/whatsapp/", {"variacao": bruto})
    texto = parse_qs(urlsplit(resposta["Location"]).query)["text"][0]
    assert texto.startswith("Oi! Vi “Bolo de pote” no Pão de Cada Dia.")
    assert "opção" not in texto


def test_titulo_com_caracteres_especiais_chega_inteiro_na_mensagem_do_whatsapp(client, make_offer):
    titulo = "Pão & Café #1 😀 100%?"
    oferta = make_offer(title=titulo, variants=[("Meio a meio / grande", 800)])
    variacao = oferta.variants.get().pk
    resposta = client.get(f"/oferta/{oferta.pk}/whatsapp/", {"variacao": variacao})
    location = urlsplit(resposta["Location"])
    assert location.fragment == ""  # o "#" do título não virou âncora
    texto = parse_qs(location.query)["text"][0]
    assert f"“{titulo}”, opção “Meio a meio / grande”" in texto


def test_variacao_de_outra_oferta_nao_vaza_o_nome_nem_trava(client, make_offer, make_seller):
    outra = make_offer(title="Segredo da outra", variants=[("Variação secreta", 100)])
    oferta = make_offer(title="Bolo de pote", variants=[("Ninho", 800)])
    id_alheio = outra.variants.get().pk
    resposta = client.get(f"/oferta/{oferta.pk}/whatsapp/", {"variacao": id_alheio})
    texto = parse_qs(urlsplit(resposta["Location"]).query)["text"][0]
    assert "secreta" not in texto and "Segredo" not in texto
    assert "opção" not in texto
    # Repetido: vale o último; se for da própria oferta, entra.
    proprio = oferta.variants.get().pk
    resposta = client.get(f"/oferta/{oferta.pk}/whatsapp/?variacao={id_alheio}&variacao={proprio}")
    assert "opção “Ninho”" in parse_qs(urlsplit(resposta["Location"]).query)["text"][0]


# WhatsApp: DDD e formato ---------------------------------------------------------------


@pytest.mark.parametrize(
    "numero",
    ["(10) 91234-5678", "(00) 91234-5678", "(20) 91234-5678", "(23) 91234-5678", "(35) 81234-5678"],
    ids=["ddd 10", "ddd 00", "ddd 20", "ddd 23", "sem o 9"],
)
def test_whatsapp_com_ddd_invalido_ou_sem_9_e_recusado_no_cadastro_e_no_perfil(
    client, seller_client, numero
):
    resposta = client.post(
        "/cadastrar/",
        {
            "display_name": "Doces da Ana",
            "email": "ana@exemplo.test",
            "password": "pao-de-queijo-quentinho",
            "whatsapp": numero,
        },
    )
    assert resposta.status_code == 200
    assert erro_do_campo(resposta, "whatsapp")
    assert not User.objects.filter(email="ana@exemplo.test").exists()

    antes = seller_client.seller.whatsapp_number
    resposta = seller_client.post(
        "/perfil/",
        {"display_name": "Nome", "whatsapp": numero, "whatsapp_public": "sim"},
    )
    assert resposta.status_code == 200
    assert erro_do_campo(resposta, "whatsapp")
    seller_client.seller.refresh_from_db()
    assert seller_client.seller.whatsapp_number == antes


@pytest.mark.parametrize(
    "numero",
    ["+55 (35) 91234-5678", "55 35 91234 5678", "35912345678", "(35)9 1234-5678", "035 91234-5678"],
)
def test_whatsapp_valido_em_formatos_comuns_e_normalizado(client, numero):
    resposta = client.post(
        "/cadastrar/",
        {
            "display_name": "Doces da Ana",
            "email": "ana@exemplo.test",
            "password": "pao-de-queijo-quentinho",
            "whatsapp": numero,
        },
    )
    assert resposta.status_code == 302
    assert Seller.objects.get().whatsapp_number == "5535912345678"


# Upload com extensão trocada ----------------------------------------------------------------


def enviar(cliente, nome, conteudo, tipo="image/jpeg", **extra):
    arquivo = SimpleUploadedFile(nome, conteudo, content_type=tipo)
    return cliente.post(NEW_URL, corpo_do_anuncio(photos=arquivo, **extra))


def test_png_com_nome_jpg_e_aceito_pelo_conteudo_e_guardado_como_webp(seller_client, png_bytes):
    resposta = enviar(seller_client, "foto.jpg", png_bytes)
    assert resposta.status_code == 302
    imagem = OfferPhoto.objects.get()
    for campo in (imagem.card_image, imagem.page_image):
        assert campo.name.endswith(".webp")
        assert "foto" not in campo.name


@pytest.mark.parametrize(
    ("nome", "tipo", "conteudo"),
    [
        ("foto.png", "image/png", make_image_bytes("GIF", (40, 40))),
        ("foto.jpg", "image/jpeg", b"%PDF-1.7\n" + b"0" * 500),
        ("foto.jpeg", "image/jpeg", b"<html><script>alert(1)</script></html>" * 20),
        ("foto.webp", "image/webp", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
        ("foto.jpg", "image/jpeg", b"MZ\x90\x00" + b"\x00" * 300),
        ("foto.jpg", "image/jpeg", b""),
    ],
    ids=[
        "gif como png",
        "pdf como jpg",
        "html como jpeg",
        "svg como webp",
        "exe como jpg",
        "vazio",
    ],
)
def test_arquivo_que_nao_e_foto_aceita_e_recusado_e_o_resto_do_formulario_volta(
    seller_client, nome, tipo, conteudo
):
    resposta = enviar(seller_client, nome, conteudo, tipo, title="Bolo preservado")
    assert resposta.status_code == 200
    assert not Offer.objects.exists()
    assert not OfferPhoto.objects.exists()
    assert erro_do_campo(resposta, "photos")
    assert parse_html(resposta).find("input", name="title").get("value") == "Bolo preservado"


def test_jpeg_com_script_colado_no_fim_e_regravado_sem_o_script(seller_client, jpeg_bytes):
    resposta = enviar(seller_client, "foto.jpg", jpeg_bytes + b"<script>alert(1)</script>")
    assert resposta.status_code == 302
    imagem = OfferPhoto.objects.get()
    for campo in (imagem.card_image, imagem.page_image):
        with default_storage.open(campo.name) as arquivo:
            assert b"<script>" not in arquivo.read()


@pytest.mark.parametrize(
    "nome", ["../../etc/passwd.jpg", "foto.php.jpg", "a" * 300 + ".jpg", "c:\\x.jpg"]
)
def test_nome_de_arquivo_malicioso_nao_chega_ao_armazenamento(seller_client, jpeg_bytes, nome):
    resposta = enviar(seller_client, nome, jpeg_bytes)
    if resposta.status_code == 302:
        imagem = OfferPhoto.objects.get()
        for campo in (imagem.card_image, imagem.page_image):
            assert ".." not in campo.name and "passwd" not in campo.name and "php" not in campo.name
    else:
        assert resposta.status_code == 200
        assert erro_do_campo(resposta, "photos")
        assert not Offer.objects.exists()
