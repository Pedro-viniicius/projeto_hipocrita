"""Verificação independente das correções da rodada 1 (qa, rodada 2).

Cada teste ataca uma correção por um caminho diferente do que o `dev` testou:
pela vitrine, com o relógio fixo, em fuso diferente de UTC e com combinações de
estado. Complementa `test_casos_de_borda.py` e os testes por área.
"""

from datetime import time

import pytest
import time_machine
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, Offer
from apps.core.testing import parse_html
from apps.metrics.models import DailySearchMiss
from conftest import DEFAULT_WHATSAPP
from texts import seller as seller_texts

pytestmark = pytest.mark.django_db

BROWSER = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"}
MANHA = "2026-11-05 10:00:00-03:00"


def titulos(response) -> list[str]:
    return [h.text for h in parse_html(response).find_all("h3", class_="cartao-oferta__titulo")]


def selos(response) -> list[str]:
    return [el.text.strip() for el in parse_html(response).find_all(class_="selo")]


# S8: o 302 entrega o número, então o limite não pode ter método de fuga ---------------


def test_head_nao_contorna_o_limite_de_contatos_por_hora(client, make_offer):
    oferta = make_offer()
    url = f"/oferta/{oferta.pk}/whatsapp/"
    with time_machine.travel(MANHA, tick=False):
        for _ in range(60):
            assert client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.7").status_code == 302
        assert client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.7").status_code == 429
        cabecalho = client.head(url, headers=BROWSER, REMOTE_ADDR="10.7.7.7")
        assert cabecalho.status_code == 429
        assert "Location" not in cabecalho
        assert DEFAULT_WHATSAPP not in cabecalho.get("Location", "")


def test_contatos_de_ips_diferentes_nao_dividem_o_limite(client, make_offer):
    oferta = make_offer()
    url = f"/oferta/{oferta.pk}/whatsapp/"
    with time_machine.travel(MANHA, tick=False):
        for _ in range(60):
            client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.7")
        assert client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.7").status_code == 429
        assert client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.8").status_code == 302


def test_o_429_do_contato_nao_vaza_o_numero(client, make_offer):
    oferta = make_offer()
    url = f"/oferta/{oferta.pk}/whatsapp/"
    with time_machine.travel(MANHA, tick=False):
        for _ in range(60):
            client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.9")
        bloqueado = client.get(url, headers=BROWSER, REMOTE_ADDR="10.7.7.9")
    assert bloqueado.status_code == 429
    assert DEFAULT_WHATSAPP not in bloqueado.content.decode()
    assert "Location" not in bloqueado


# Decisão 2: oferta do dia esgotada só mostra o selo no dia em que foi marcada ---------


def esgotada_do_dia(make_offer, marcada_em: str) -> Offer:
    from datetime import datetime

    return make_offer(
        kind="daily",
        title="Marmita do dia",
        status="sold_out",
        status_changed_at=datetime.fromisoformat(marcada_em),
        closing_time=time(18, 0),
    )


def test_esgotada_do_dia_marcada_a_noite_ainda_tem_selo_ate_a_meia_noite_local(client, make_offer):
    # 22:00 em São Paulo já é 01:00 do dia seguinte em UTC: o "dia" é o da comunidade.
    oferta = esgotada_do_dia(make_offer, "2026-11-05 22:00:00-03:00")
    with time_machine.travel("2026-11-05 23:58:00-03:00", tick=False):
        assert "Esgotado" in selos(client.get("/"))
        assert "Esgotado" in client.get(f"/oferta/{oferta.pk}/").content.decode()
    with time_machine.travel("2026-11-06 00:01:00-03:00", tick=False):
        assert "Esgotado" not in selos(client.get("/"))


def test_esgotada_do_dia_no_dia_seguinte_fica_listada_sem_selo_e_sem_contato(client, make_offer):
    oferta = esgotada_do_dia(make_offer, "2026-11-05 09:00:00-03:00")
    with time_machine.travel("2026-11-06 09:00:00-03:00", tick=False):
        home = client.get("/")
        assert "Marmita do dia" in titulos(home)
        assert selos(home) == []
        pagina = client.get(f"/oferta/{oferta.pk}/")
        assert pagina.status_code == 200
        assert "Esta oferta está esgotada no momento." in pagina.content.decode()
        assert parse_html(pagina).find("button", string="Consultar no WhatsApp") is None
        assert client.get(f"/oferta/{oferta.pk}/whatsapp/", headers=BROWSER).status_code == 404
        # Fora de "Disponíveis hoje": sem confirmação não é disponível.
        assert "Marmita do dia" not in titulos(client.get("/?hoje=1"))


def test_esgotada_recorrente_continua_com_selo_nos_dias_seguintes(client, make_offer):
    # A decisão 2 vale só para a oferta do dia.
    make_offer(
        kind="recurring",
        title="Brigadeiro",
        status="sold_out",
        status_changed_at="2026-11-01T12:00:00-03:00",
    )
    with time_machine.travel("2026-11-06 09:00:00-03:00", tick=False):
        assert selos(client.get("/")) == ["Esgotado"]


def test_vendedor_continua_vendo_esgotado_quando_o_publico_ja_nao_ve(seller_client, make_offer):
    make_offer(
        seller_client.seller,
        kind="daily",
        title="Marmita do dia",
        status="sold_out",
        status_changed_at="2026-11-05T09:00:00-03:00",
    )
    with time_machine.travel("2026-11-06 09:00:00-03:00", tick=False):
        painel = seller_client.get("/meus-anuncios/")
    assert "Esgotado" in painel.content.decode()


# Decisão 1: categoria escondida some só como chip ---------------------------------------


def test_categoria_escondida_so_perde_o_chip(client, make_offer):
    categoria = Category.objects.get(slug="bebidas")
    oferta = make_offer(title="Suco de acerola", category=categoria)
    categoria.is_active = False
    categoria.save()
    home = client.get("/")
    chips = [a.text for a in parse_html(home).find_all("a", class_="chip")]
    assert not any("Bebidas" in chip for chip in chips)
    assert "Suco de acerola" in titulos(home)
    assert "Suco de acerola" in titulos(client.get("/?q=acerola"))
    assert client.get(f"/oferta/{oferta.pk}/").status_code == 200
    # Link antigo com a categoria escondida não quebra: a lista aparece inteira.
    antigo = client.get("/?cat=bebidas")
    assert antigo.status_code == 200
    assert "Suco de acerola" in titulos(antigo)


# R9: busca sem resultado só conta quando o termo é o culpado ----------------------------


@pytest.mark.parametrize("consulta", ["?q=zzzinexistente&hoje=1", "?q=zzzinexistente&cat=bebidas"])
def test_busca_vazia_com_filtro_nao_vira_demanda_nao_atendida(client, make_offer, consulta):
    make_offer(title="Suco")
    client.get(f"/{consulta}", headers=BROWSER)
    assert not DailySearchMiss.objects.exists()


def test_busca_vazia_pura_grava_uma_vez_por_termo_normalizado(client, make_offer):
    make_offer(title="Suco")
    for termo in ("Zzzinexistente", "zzzínexistente", "  ZZZINEXISTENTE "):
        client.get("/", {"q": termo}, headers=BROWSER)
    linha = DailySearchMiss.objects.get()
    assert (linha.term, linha.count) == ("zzzinexistente", 3)


def test_robo_nao_grava_busca_sem_resultado(client):
    client.get("/?q=zzzinexistente", headers={"user-agent": "Googlebot/2.1 bot"})
    assert not DailySearchMiss.objects.exists()


# Q1: caracteres de controle na busca ------------------------------------------------------


@pytest.mark.parametrize("controle", ["%00", "%01", "%1f", "%7f", "%0a", "%0d", "%09"])
def test_busca_com_caractere_de_controle_responde_200_e_nao_grava_controle(client, controle):
    resposta = client.get(f"/?q=bolo{controle}rosa", headers=BROWSER)
    assert resposta.status_code == 200
    for linha in DailySearchMiss.objects.all():
        assert not any(ord(c) < 32 or ord(c) == 127 for c in linha.term)


def test_busca_so_com_nul_nao_grava_nada(client):
    assert client.get("/?q=%00%00", headers=BROWSER).status_code == 200
    assert not DailySearchMiss.objects.exists()


def test_busca_nul_no_meio_ainda_acha_a_oferta(client, make_offer):
    make_offer(title="Bolo rosa")
    resposta = client.get("/?q=bolo%00rosa")
    assert resposta.status_code == 200
    assert "Bolo rosa" in titulos(resposta)


# R1/R2/R5: edição que troca o tipo ou mexe em anúncio oculto -----------------------------


def corpo(offer: Offer, **extra) -> dict:
    base = {
        "kind": offer.kind,
        "title": offer.title,
        "category": offer.category_id,
        "price": "10,00",
        "fulfillment": offer.fulfillment,
    }
    return base | extra


def test_oculto_do_dia_editado_com_confirmar_marcado_responde_sem_500(seller_client, make_offer):
    oferta = make_offer(
        seller_client.seller,
        kind="daily",
        closing_time=time(18, 0),
        hidden_at="2026-11-04T09:00:00-03:00",
    )
    with time_machine.travel(MANHA, tick=False):
        resposta = seller_client.post(
            f"/meus-anuncios/{oferta.pk}/editar/",
            corpo(oferta, title="Novo título", closing_time="18:00", confirm_today="on"),
        )
    assert resposta.status_code == 302
    oferta.refresh_from_db()
    assert oferta.title == "Novo título"
    assert oferta.daily_confirmed_on is None
    assert oferta.hidden_at is not None


def test_recorrente_confirmado_vira_do_dia_desmarcado_sai_de_disponiveis_hoje(
    seller_client, client, make_offer
):
    oferta = make_offer(
        seller_client.seller, kind="recurring", title="Doce fixo", daily_confirmed_on="2026-11-05"
    )
    with time_machine.travel(MANHA, tick=False):
        assert "Doce fixo" in titulos(client.get("/?hoje=1"))
        seller_client.post(
            f"/meus-anuncios/{oferta.pk}/editar/",
            corpo(oferta, kind="daily", closing_time="18:00"),
        )
        assert "Doce fixo" not in titulos(client.get("/?hoje=1"))


def test_do_dia_passado_do_horario_vira_recorrente_nao_volta_a_disponivel_hoje(
    seller_client, client, make_offer
):
    oferta = make_offer(
        seller_client.seller,
        kind="daily",
        title="Marmita",
        closing_time=time(14, 0),
        daily_confirmed_on="2026-11-05",
    )
    with time_machine.travel("2026-11-05 15:00:00-03:00", tick=False):
        seller_client.post(f"/meus-anuncios/{oferta.pk}/editar/", corpo(oferta, kind="recurring"))
        assert "Marmita" not in titulos(client.get("/?hoje=1"))
        assert selos(client.get("/")) == ["Sob encomenda"]


def test_esgotado_que_vira_venda_unica_fica_ativo_e_contatavel(seller_client, client, make_offer):
    oferta = make_offer(seller_client.seller, kind="recurring", status="sold_out")
    with time_machine.travel(MANHA, tick=False):
        seller_client.post(f"/meus-anuncios/{oferta.pk}/editar/", corpo(oferta, kind="one_off"))
        oferta.refresh_from_db()
        assert oferta.status == "active"
        assert client.get(f"/oferta/{oferta.pk}/whatsapp/", headers=BROWSER).status_code == 302


# R4: "disponível hoje" a partir de 23:59 ------------------------------------------------


def test_confirmar_as_2359_pelo_botao_e_recusado_sem_gravar(seller_client, make_offer):
    oferta = make_offer(seller_client.seller, kind="recurring")
    with time_machine.travel("2026-11-05 23:59:10-03:00", tick=False):
        resposta = seller_client.post(
            f"/meus-anuncios/{oferta.pk}/acao/", {"action": "confirm_today"}, follow=True
        )
    oferta.refresh_from_db()
    assert oferta.daily_confirmed_on is None
    assert "Pronto" not in resposta.content.decode()


def test_confirmar_as_235858_ainda_vale(seller_client, client, make_offer):
    oferta = make_offer(seller_client.seller, kind="recurring", title="Última hora")
    with time_machine.travel("2026-11-05 23:58:58-03:00", tick=False):
        seller_client.post(f"/meus-anuncios/{oferta.pk}/acao/", {"action": "confirm_today"})
        assert "Última hora" in titulos(client.get("/?hoje=1"))


# S1: tetos de anúncios, pela porta da frente -----------------------------------------------

NOVO = "/meus-anuncios/novo/"


def corpo_novo(**extra) -> dict:
    return {
        "kind": "recurring",
        "title": "Brownie",
        "category": Category.objects.get(slug="comidas-e-doces").pk,
        "price": "5,00",
        "fulfillment": "Retirada",
    } | extra


def vendedor_logado(make_seller, **campos) -> Client:
    vendedor = make_seller(**campos)
    cliente = Client()
    cliente.force_login(vendedor.user)
    cliente.seller = vendedor
    return cliente


def test_vendedor_novo_nao_passa_de_3_pendentes_e_nada_e_gravado_no_4o(make_seller):
    cliente = vendedor_logado(make_seller, trusted=False)
    for n in range(3):
        assert cliente.post(NOVO, corpo_novo(title=f"Brownie {n}")).status_code == 302
    quarto = cliente.post(NOVO, corpo_novo(title="Brownie 3"))
    assert quarto.status_code == 200
    assert Offer.objects.filter(seller=cliente.seller).count() == 3
    # O formulário volta com o que foi digitado.
    assert 'value="Brownie 3"' in quarto.content.decode()


def test_aprovar_o_primeiro_anuncio_libera_o_limite_de_pendentes(make_seller):
    cliente = vendedor_logado(make_seller, trusted=False)
    for n in range(3):
        cliente.post(NOVO, corpo_novo(title=f"Brownie {n}"))
    primeiro = Offer.objects.filter(seller=cliente.seller).order_by("pk").first()
    from apps.moderation import services as moderacao

    admin = User.objects.create_user(email="admin@exemplo.test", password="x" * 12, is_staff=True)
    moderacao.approve_offer(primeiro.pk, by=admin, now=timezone.now())
    cliente.seller.refresh_from_db()
    assert cliente.seller.is_trusted
    assert cliente.post(NOVO, corpo_novo(title="Brownie 4")).status_code == 302


def test_limite_de_30_anuncios_conta_pausados_ocultos_e_vendidos(make_seller, make_offer):
    cliente = vendedor_logado(make_seller)
    estados = [
        {"status": "paused"},
        {"status": "sold_out"},
        {"status": "sold", "kind": "one_off"},
        {"hidden_at": "2026-11-01T10:00:00-03:00"},
    ]
    for n in range(30):
        make_offer(cliente.seller, **estados[n % 4])
    recusado = cliente.post(NOVO, corpo_novo())
    assert recusado.status_code == 200
    assert Offer.objects.filter(seller=cliente.seller).count() == 30


def test_o_teto_de_30_e_por_vendedor_e_nao_global(make_seller, make_offer):
    cheio = make_seller()
    for _ in range(30):
        make_offer(cheio)
    outro = vendedor_logado(make_seller)
    assert outro.post(NOVO, corpo_novo()).status_code == 302


# S9: trocar o nome troca o link público ---------------------------------------------------


def perfil(cliente: Client, **campos):
    vendedor = cliente.seller
    dados = {
        "display_name": vendedor.display_name,
        "bio": "",
        "service_area": "",
        "hours": "",
        "whatsapp": "(35) 91234-5678",
        "whatsapp_public": "sim",
    } | campos
    return cliente.post("/perfil/", dados, follow=True)


def test_trocar_so_a_caixa_do_nome_nao_muda_o_link_nem_avisa(make_seller):
    cliente = vendedor_logado(make_seller, display_name="Doces da Ana")
    antes = cliente.seller.slug
    resposta = perfil(cliente, display_name="DOCES DA ANA")
    cliente.seller.refresh_from_db()
    assert cliente.seller.slug == antes
    assert seller_texts.PROFILE_LINK_CHANGED not in resposta.content.decode()
    assert seller_texts.PROFILE_SAVED in resposta.content.decode()
    assert Client().get(f"/vendedor/{antes}/").status_code == 200


def test_nome_novo_que_colide_com_outro_vendedor_ganha_sufixo_e_o_link_antigo_da_404(
    make_seller, make_offer
):
    make_seller(display_name="Doces da Mari")  # já ocupa "doces-da-mari"
    cliente = vendedor_logado(make_seller, display_name="Maria Silva Souza")
    make_offer(cliente.seller)
    antigo = cliente.seller.slug
    perfil(cliente, display_name="Doces da Mari")
    cliente.seller.refresh_from_db()
    assert cliente.seller.slug == "doces-da-mari-2"
    publico = Client()
    assert publico.get(f"/vendedor/{antigo}/").status_code == 404
    assert publico.get("/vendedor/doces-da-mari-2/").status_code == 200
    # O nome civil antigo não sobra em nenhuma página pública.
    assert "Maria Silva Souza" not in publico.get("/").content.decode()


def test_nome_so_com_simbolos_e_recusado_e_o_link_nao_muda(make_seller):
    cliente = vendedor_logado(make_seller, display_name="Doces da Ana")
    antes = cliente.seller.slug
    resposta = perfil(cliente, display_name="!!! ???")
    assert resposta.status_code == 200
    cliente.seller.refresh_from_db()
    assert (cliente.seller.slug, cliente.seller.display_name) == (antes, "Doces da Ana")


# Decisão 3: pausar um anúncio esgotado e reativar volta para ativo ----------------------


@pytest.mark.parametrize("tipo", ["recurring", "daily"])
def test_pausar_esgotado_e_reativar_volta_para_ativo_e_contatavel(
    seller_client, client, make_offer, tipo
):
    oferta = make_offer(seller_client.seller, kind=tipo, status="sold_out", title="Acabou")
    acao = f"/meus-anuncios/{oferta.pk}/acao/"
    with time_machine.travel(MANHA, tick=False):
        seller_client.post(acao, {"action": "pause"})
        oferta.refresh_from_db()
        assert oferta.status == "paused"
        assert client.get(f"/oferta/{oferta.pk}/").status_code == 404
        seller_client.post(acao, {"action": "resume"})
        oferta.refresh_from_db()
        assert oferta.status == "active"
        assert client.get(f"/oferta/{oferta.pk}/whatsapp/", headers=BROWSER).status_code == 302


# S1 sob concorrência: o teto vale mesmo com envios simultâneos (só faz sentido no PostgreSQL,
# onde `select_for_update` trava a linha; no SQLite a gravação já é serializada) ------------


@pytest.mark.django_db(transaction=True)
def test_envios_simultaneos_nao_furam_o_teto_de_30_anuncios(make_seller, make_offer):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from zoneinfo import ZoneInfo

    from django.db import connection, connections

    from apps.catalog.services_seller import OfferLimitReached, create_offer

    if connection.vendor != "postgresql":
        pytest.skip("trava de linha só existe no PostgreSQL (rode com POSTGRES_HOST definido)")

    vendedor = make_seller()
    for _ in range(29):
        make_offer(vendedor)
    categoria = Category.objects.get(slug="comidas-e-doces")
    dados = {
        "kind": "recurring",
        "title": "Simultâneo",
        "category": categoria,
        "price": 500,
        "description": "",
        "fulfillment": "Retirada",
        "portion": "",
        "ingredients": "",
        "allergens": "",
        "closing_time": None,
        "confirm_today": False,
        "variants": [],
    }
    largada = Barrier(6)
    agora = timezone.now()

    def enviar(_):
        try:
            largada.wait(timeout=10)
            create_offer(vendedor, dados, [], agora, ZoneInfo("America/Sao_Paulo"))
            return "criado"
        except OfferLimitReached:
            return "recusado"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = list(pool.map(enviar, range(6)))
    assert resultados.count("criado") == 1
    assert resultados.count("recusado") == 5
    assert Offer.objects.filter(seller=vendedor).count() == 30
