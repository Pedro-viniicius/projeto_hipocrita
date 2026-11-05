"""Cadastro de vendedor (CA6, CA8, CA14)."""

import logging
import re
from datetime import timedelta

import pytest
import time_machine
from django.contrib.messages import get_messages
from django.test import Client

from apps.accounts.models import User
from apps.catalog.models import Seller
from apps.core.models import RateLimitCounter
from apps.core.testing import assert_accessible_page, parse_html
from texts import accounts as texts

pytestmark = pytest.mark.django_db

URL = "/cadastrar/"
PASSWORD = "pao-de-queijo-quentinho"


def payload(**overrides) -> dict:
    data = {
        "display_name": "Doces da Ana",
        "email": "ana@exemplo.test",
        "password": PASSWORD,
        "whatsapp": "(35) 91234-5678",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def field_error(response, name: str) -> str:
    """Texto da lista de erros ligada ao campo (`id_<nome>_error`)."""
    el = parse_html(response).find(id=f"id_{name}_error")
    return el.text if el is not None else ""


def test_get_renders_accessible_form_with_authorization_unchecked(client):
    response = client.get(URL)
    assert response.status_code == 200
    assert_accessible_page(response)
    doc = parse_html(response)
    checkbox = doc.find("input", name="whatsapp_public")
    assert checkbox is not None
    assert checkbox.get("type") == "checkbox"
    assert not checkbox.has("checked")
    phone = doc.find("input", name="whatsapp")
    assert phone.get("inputmode") == "tel"
    assert doc.find("input", name="password").get("autocomplete") == "new-password"


def test_signup_creates_user_and_seller_and_logs_in(client):
    response = client.post(URL, payload())
    assert response.status_code == 302
    assert response["Location"] == "/meus-anuncios/"

    user = User.objects.get()
    assert user.email == "ana@exemplo.test"
    assert user.check_password(PASSWORD)
    seller = Seller.objects.get(user=user)
    assert seller.display_name == "Doces da Ana"
    assert seller.slug == "doces-da-ana"
    assert seller.whatsapp_number == "5535912345678"
    # CA6: sem marcar, o número não é exibido.
    assert seller.whatsapp_public is False
    assert seller.whatsapp_public_changed_at is None
    assert seller.is_trusted is False
    assert seller.is_demo is False

    assert client.session["_auth_user_id"] == str(user.pk)
    texts_shown = [str(m) for m in get_messages(response.wsgi_request)]
    assert texts_shown == [texts.SIGNUP_OK]


def test_signup_with_authorization_records_when(client):
    client.post(URL, payload(whatsapp_public="on"))
    seller = Seller.objects.get()
    assert seller.whatsapp_public is True
    assert seller.whatsapp_public_changed_at is not None


def test_email_is_normalized(client):
    client.post(URL, payload(email="  Ana@Exemplo.TEST "))
    assert User.objects.get().email == "ana@exemplo.test"


def test_same_name_gets_unique_slug(client, make_seller):
    make_seller(display_name="Doces da Ana", slug="doces-da-ana")
    client.post(URL, payload())
    assert Seller.objects.get(user__email="ana@exemplo.test").slug == "doces-da-ana-2"


def test_invalid_whatsapp_keeps_everything_and_shows_error_next_to_field(client):
    response = client.post(URL, payload(whatsapp="(35) 3821-1234", whatsapp_public="on"))
    assert response.status_code == 200
    assert not User.objects.exists()
    assert not Seller.objects.exists()

    doc = parse_html(response)
    # CA8: tudo volta preenchido, menos a senha.
    assert doc.find("input", name="display_name").get("value") == "Doces da Ana"
    assert doc.find("input", name="email").get("value") == "ana@exemplo.test"
    assert doc.find("input", name="whatsapp").get("value") == "(35) 3821-1234"
    assert doc.find("input", name="whatsapp_public").has("checked")
    assert doc.find("input", name="password").get("value") is None
    assert PASSWORD not in response.content.decode()

    # Erro junto do campo, ligado por aria-describedby, e resumo no topo.
    assert texts.WHATSAPP_INVALID in field_error(response, "whatsapp")
    phone = doc.find("input", name="whatsapp")
    assert phone.get("aria-invalid") == "true"
    assert "id_whatsapp_error" in phone.get("aria-describedby")
    summary = doc.find(role="alert")
    assert summary is not None
    assert "Corrija 1 campo para continuar." in summary.text
    assert summary.find("a", href="#id_whatsapp") is not None
    assert_accessible_page(response)


def test_required_fields(client):
    response = client.post(URL, {})
    assert response.status_code == 200
    for name in ("display_name", "email", "password", "whatsapp"):
        assert texts.REQUIRED in field_error(response, name)
    assert "Corrija 4 campos para continuar." in response.content.decode()


def test_invalid_email(client):
    response = client.post(URL, payload(email="ana@"))
    assert texts.EMAIL_INVALID in field_error(response, "email")


@pytest.mark.parametrize(
    "email", ["demo-doces@exemplo.invalid", "demo-doces@EXEMPLO.INVALID", "ana@outro.invalid"]
)
def test_reserved_invalid_domain_is_refused(client, email):
    """As contas de exemplo usam `.invalid`: ninguém pode se cadastrar com esse domínio."""
    response = client.post(URL, payload(email=email))
    assert response.status_code == 200
    assert texts.EMAIL_INVALID in field_error(response, "email")
    assert not User.objects.exists()


def test_authorization_help_says_offers_need_it(client):
    """D4: quem não autoriza precisa saber, já no cadastro, que os anúncios não aparecem."""
    assert "seus anúncios não aparecem na vitrine" in client.get(URL).content.decode()


def test_duplicate_email_case_insensitive(client, make_user):
    make_user(email="ana@exemplo.test")
    response = client.post(URL, payload(email="ANA@exemplo.test"))
    assert response.status_code == 200
    assert texts.EMAIL_TAKEN in field_error(response, "email")
    assert User.objects.count() == 1


def test_short_password_uses_spec_message(client):
    response = client.post(URL, payload(password="curta1!"))
    assert texts.PASSWORD_TOO_SHORT in field_error(response, "password")
    assert not User.objects.exists()


def test_common_password_rejected(client):
    response = client.post(URL, payload(password="12345678"))
    assert field_error(response, "password")
    assert not User.objects.exists()


def test_name_without_letters_rejected(client):
    response = client.post(URL, payload(display_name="!!!"))
    assert texts.NAME_INVALID in field_error(response, "display_name")


def test_logged_in_user_is_redirected(seller_client):
    response = seller_client.get(URL)
    assert response.status_code == 302
    assert response["Location"] == "/meus-anuncios/"


# CA14: limite por IP e CSRF ----------------------------------------------------


def test_signup_limited_to_5_per_hour_per_ip(client):
    for i in range(5):
        client.post(URL, payload(email=f"p{i}@exemplo.test", whatsapp="x"), REMOTE_ADDR="10.0.0.1")
    blocked = client.post(URL, payload(), REMOTE_ADDR="10.0.0.1")
    assert blocked.status_code == 429
    assert not User.objects.exists()
    # Outro IP continua podendo se cadastrar.
    other = client.post(URL, payload(), REMOTE_ADDR="10.0.0.2")
    assert other.status_code == 302
    # Só o HMAC do IP fica guardado.
    assert all(len(row.key_hash) == 64 for row in RateLimitCounter.objects.all())
    assert not RateLimitCounter.objects.filter(key_hash__contains="10.0.0").exists()


def test_signups_per_day_has_a_global_cap(settings):
    # S1: teto de contas novas por dia, somado entre todos os IPs.
    settings.SIGNUPS_PER_DAY = 2
    with time_machine.travel("2026-11-05 12:00:00+00:00", tick=False) as traveller:
        for i in range(2):
            ok = Client().post(URL, payload(email=f"p{i}@exemplo.test"), REMOTE_ADDR=f"10.0.0.{i}")
            assert ok.status_code == 302
        blocked = Client().post(URL, payload(email="p9@exemplo.test"), REMOTE_ADDR="10.0.0.9")
        assert blocked.status_code == 429
        assert blocked["Retry-After"] == str(12 * 3600)  # até a virada do dia em UTC
        assert texts.SIGNUP_DAILY_LIMIT in blocked.content.decode()
        assert_accessible_page(blocked)
        assert User.objects.count() == 2
        # Quem abre o formulário já vê o aviso.
        page = Client().get(URL)
        assert page.status_code == 200
        assert texts.SIGNUP_DAILY_LIMIT in page.content.decode()
        # No dia seguinte o cadastro reabre.
        traveller.shift(timedelta(hours=12))
        again = Client().post(URL, payload(email="p9@exemplo.test"), REMOTE_ADDR="10.0.0.9")
        assert again.status_code == 302
    keys = RateLimitCounter.objects.filter(scope="signup_day").values_list("key_hash", flat=True)
    assert keys and all(len(key) == 64 for key in keys)


def test_signup_cap_counts_only_created_accounts(settings):
    # Envios inválidos não gastam o teto do dia (senão qualquer um fecharia o cadastro).
    settings.SIGNUPS_PER_DAY = 1
    for i in range(4):
        Client().post(URL, payload(whatsapp="x"), REMOTE_ADDR=f"10.0.1.{i}")
    assert Client().post(URL, payload(), REMOTE_ADDR="10.0.2.1").status_code == 302
    blocked = Client().post(URL, payload(email="b@exemplo.test"), REMOTE_ADDR="10.0.2.2")
    assert blocked.status_code == 429


def test_signup_closed_with_zero_per_day(client, settings):
    settings.SIGNUPS_PER_DAY = 0
    page = client.get(URL).content.decode()
    assert texts.SIGNUP_CLOSED in page
    assert texts.SIGNUP_DAILY_LIMIT not in page
    assert client.post(URL, payload()).status_code == 429
    assert not User.objects.exists()


def _cap_responses(settings, per_day: int) -> tuple:
    """GET e POST do cadastro com o teto do dia já gasto (`per_day=0`: fechado)."""
    settings.SIGNUPS_PER_DAY = per_day
    with time_machine.travel("2026-11-05 12:00:00+00:00", tick=False):
        for i in range(per_day):
            ok = Client().post(URL, payload(email=f"t{i}@exemplo.test"), REMOTE_ADDR=f"10.0.4.{i}")
            assert ok.status_code == 302
        get = Client().get(URL)
        post = Client().post(URL, payload(email="t9@exemplo.test"), REMOTE_ADDR="10.0.4.9")
    return get, post


@pytest.mark.parametrize(
    ("per_day", "message"),
    [(0, texts.SIGNUP_CLOSED), (1, texts.SIGNUP_DAILY_LIMIT)],
    ids=["fechado", "teto-do-dia"],
)
def test_daily_cap_is_information_not_a_user_error(settings, per_day, message):
    # D5: cadastro fechado ou teto do dia não é erro de quem chegou: aviso informativo,
    # sem role="alert".
    for response in _cap_responses(settings, per_day):
        doc = parse_html(response)
        notice = doc.find("div", class_="aviso--info")
        assert notice is not None
        assert notice.get("role") == "status"
        assert message in notice.text
        assert doc.find("div", class_="aviso--error") is None
        assert doc.find(role="alert") is None
        assert_accessible_page(response)


@pytest.mark.parametrize(
    ("per_day", "lead"),
    [
        (0, "Para pedir uma conta, fale com a administração pelo e-mail"),
        (1, "Se precisar antes disso, fale com a administração pelo e-mail"),
    ],
    ids=["fechado", "teto-do-dia"],
)
def test_closed_or_capped_signup_shows_the_contact_as_a_link_on_get_and_post(
    settings, per_day, lead
):
    settings.PRIVACY_CONTACT_EMAIL = "contato@exemplo.test"
    get, post = _cap_responses(settings, per_day)
    assert post.status_code == 429
    for response in (get, post):
        notice = parse_html(response).find("div", class_="aviso--info")
        assert lead in notice.text
        link = notice.find("a", href="mailto:contato@exemplo.test")
        assert link is not None
        assert link.text == "contato@exemplo.test"
        assert "Ainda não há um contato" not in notice.text


@pytest.mark.parametrize(
    ("per_day", "honest"),
    [
        (0, "Ainda não há um contato cadastrado para pedir uma conta."),
        (1, "Ainda não há um contato cadastrado para pedir uma conta antes disso."),
    ],
    ids=["fechado", "teto-do-dia"],
)
def test_closed_or_capped_signup_without_contact_says_so_on_get_and_post(settings, per_day, honest):
    settings.PRIVACY_CONTACT_EMAIL = ""
    get, post = _cap_responses(settings, per_day)
    assert post.status_code == 429
    for response in (get, post):
        notice = parse_html(response).find("div", class_="aviso--info")
        assert honest in notice.text
        assert "fale com a administração" not in notice.text
        assert notice.find("a") is None


# R16: cadastro fechado (SIGNUPS_PER_DAY=0) não é "teto de hoje" e não promete reabertura -------

FORBIDDEN_IN_CLOSED = ("hoje", "esgotaram", "amanhã", "amanha", "reabr", "volte", "tente de novo")


def test_closed_signup_says_it_is_closed_without_form_or_promise(client, settings):
    settings.SIGNUPS_PER_DAY = 0
    settings.PRIVACY_CONTACT_EMAIL = "contato@exemplo.test"
    for response in (client.get(URL), client.post(URL, payload())):
        doc = parse_html(response)
        notice = doc.find("div", class_="aviso--info")
        assert notice is not None
        text = notice.text.lower()
        assert "fechad" in text
        for word in FORBIDDEN_IN_CLOSED:
            assert word not in text, f"aviso de cadastro fechado não pode dizer {word!r}"
        # Sem formulário: ninguém preenche à toa.
        assert doc.find("input", attrs={"name": "password"}) is None
        # O contato continua aparecendo.
        assert notice.find("a", href="mailto:contato@exemplo.test") is not None


def test_closed_signup_does_not_promise_reopening_in_retry_after(client, settings):
    # Sem teto "por dia", não há hora em que o cadastro volte: Retry-After seria promessa falsa.
    settings.SIGNUPS_PER_DAY = 0
    response = client.post(URL, payload())
    assert response.status_code == 429
    assert "Retry-After" not in response
    assert not User.objects.exists()


def test_closed_signup_answers_before_the_ip_limit_and_stores_nothing(client, settings):
    # R3: passar do limite de 5/h por IP não troca o aviso de fechado pelo 429 genérico
    # ("tente de novo", Retry-After), e o envio nem grava o código do IP.
    settings.SIGNUPS_PER_DAY = 0
    for i in range(7):
        response = client.post(URL, payload(email=f"f{i}@exemplo.test"), REMOTE_ADDR="10.0.5.1")
        assert response.status_code == 429, f"envio {i + 1}"
        assert "Retry-After" not in response, f"envio {i + 1}"
        notice = parse_html(response).find("div", class_="aviso--info")
        assert notice is not None, f"envio {i + 1}"
        assert texts.SIGNUP_CLOSED in notice.text
        assert "tente de novo" not in response.content.decode().lower()
    assert not User.objects.exists()
    assert not RateLimitCounter.objects.exists()


def test_reached_daily_cap_still_counts_posts_per_ip(settings):
    # O teto do dia não muda o limite por IP: o 6º envio na hora dá o 429 genérico.
    settings.SIGNUPS_PER_DAY = 1
    with time_machine.travel("2026-11-05 12:00:00+00:00", tick=False):
        assert Client().post(URL, payload(), REMOTE_ADDR="10.0.6.1").status_code == 302
        client = Client()
        for i in range(5):
            capped = client.post(URL, payload(email=f"c{i}@exemplo.test"), REMOTE_ADDR="10.0.6.2")
            assert capped.status_code == 429
            assert texts.SIGNUP_DAILY_LIMIT in capped.content.decode()
        limited = client.post(URL, payload(email="c9@exemplo.test"), REMOTE_ADDR="10.0.6.2")
    assert limited.status_code == 429
    assert limited["Retry-After"] == "3600"
    assert texts.SIGNUP_DAILY_LIMIT not in limited.content.decode()
    assert RateLimitCounter.objects.filter(scope="signup").exists()


def test_closed_signup_without_contact_is_still_honest_and_free_of_promises(client, settings):
    settings.SIGNUPS_PER_DAY = 0
    settings.PRIVACY_CONTACT_EMAIL = ""
    notice = parse_html(client.get(URL)).find("div", class_="aviso--info")
    text = notice.text.lower()
    assert "fechad" in text
    assert "ainda não há um contato cadastrado" in text
    assert "amanhã" not in text
    assert "esgotaram" not in text


def test_reached_daily_cap_keeps_today_text_and_contact(settings):
    settings.SIGNUPS_PER_DAY = 1
    settings.PRIVACY_CONTACT_EMAIL = "contato@exemplo.test"
    with time_machine.travel("2026-11-05 12:00:00+00:00", tick=False):
        assert Client().post(URL, payload(), REMOTE_ADDR="10.0.3.1").status_code == 302
        blocked = Client().post(URL, payload(email="b@exemplo.test"), REMOTE_ADDR="10.0.3.2")
        page = Client().get(URL)
    assert blocked.status_code == 429
    assert blocked["Retry-After"] == str(12 * 3600)
    notice = parse_html(page).find("div", class_="aviso--info")
    assert "Os cadastros de hoje já se esgotaram. Tente de novo amanhã." in notice.text
    assert notice.find("a", href="mailto:contato@exemplo.test") is not None
    assert "fechad" not in notice.text.lower()


def test_whatsapp_help_says_who_sees_the_number(client):
    # D7: o que acontece se autorizar, em vez de "a menos que você autorize".
    assert "a menos que" not in texts.WHATSAPP_HELP
    help_text = parse_html(client.get(URL)).find(id="id_whatsapp_helptext").text
    assert "Só você e a administração veem o número." in help_text
    assert "quem tocar em “Consultar no WhatsApp” abre a conversa com você" in help_text


def test_csrf_required():
    client = Client(enforce_csrf_checks=True)
    assert client.post(URL, payload()).status_code == 403
    assert not User.objects.exists()

    page = client.get(URL)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    response = client.post(URL, {**payload(), "csrfmiddlewaretoken": token.group(1)})
    assert response.status_code == 302
    assert User.objects.count() == 1


def test_no_personal_data_in_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    for name in ("django", "django.request", "django.db.backends", "apps"):
        logging.getLogger(name).addHandler(caplog.handler)
    try:
        client.post(URL, payload(whatsapp="invalido"))
        client.post(URL, payload())
    finally:
        for name in ("django", "django.request", "django.db.backends", "apps"):
            logging.getLogger(name).removeHandler(caplog.handler)
    text = caplog.text
    for secret in ("ana@exemplo.test", PASSWORD, "5535912345678", "91234-5678"):
        assert secret not in text
