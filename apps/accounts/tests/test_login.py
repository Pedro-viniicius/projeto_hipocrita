"""Login por e-mail, limite de tentativas e logout (CA14)."""

import re
from datetime import timedelta

import pytest
import time_machine
from django.test import Client

from apps.accounts import views
from apps.core.models import RateLimitCounter
from apps.core.testing import assert_accessible_page, parse_html
from texts import accounts as texts

pytestmark = pytest.mark.django_db

URL = "/entrar/"
EMAIL = "ana@exemplo.test"
DEFAULT_PASSWORD = "senha-certa-da-ana-123"


@pytest.fixture
def seller(make_seller, make_user):
    return make_seller(user=make_user(email=EMAIL, password=DEFAULT_PASSWORD))


def login(client, email=EMAIL, password=DEFAULT_PASSWORD, ip="10.0.0.1", **extra):
    return client.post(URL, {"email": email, "password": password, **extra}, REMOTE_ADDR=ip)


def is_logged_in(client) -> bool:
    return "_auth_user_id" in client.session


def test_get_renders_accessible_form(client):
    response = client.get(URL)
    assert response.status_code == 200
    assert_accessible_page(response)
    doc = parse_html(response)
    assert doc.find("input", name="email").get("autocomplete") == "email"
    assert doc.find("input", name="password").get("autocomplete") == "current-password"
    assert doc.find("a", href="/senha/recuperar/") is not None
    assert doc.find("a", href="/cadastrar/") is not None


def test_login_success_goes_to_dashboard(client, seller):
    response = login(client, email="  ANA@Exemplo.test ")
    assert response.status_code == 302
    assert response["Location"] == "/meus-anuncios/"
    assert client.session["_auth_user_id"] == str(seller.user.pk)


def test_login_rotates_session_key(client, seller):
    client.get(URL)
    client.session.save()
    before = client.session.session_key
    login(client)
    assert client.session.session_key != before


def test_login_follows_safe_next_only(client, seller):
    response = login(client, next="/perfil/")
    assert response["Location"] == "/perfil/"
    client.post("/sair/")
    response = login(client, next="https://malicioso.example/roubo")
    assert response["Location"] == "/meus-anuncios/"


def test_staff_without_seller_goes_to_admin(client, make_user):
    make_user(email="admin@exemplo.test", password=DEFAULT_PASSWORD, is_staff=True)
    response = login(client, email="admin@exemplo.test")
    assert response["Location"] == "/admin/"


@pytest.mark.parametrize(
    ("email", "password"),
    [(EMAIL, "senha-errada-123"), ("ninguem@exemplo.test", DEFAULT_PASSWORD)],
)
def test_failure_message_is_generic(client, seller, email, password):
    response = login(client, email=email, password=password)
    assert response.status_code == 200
    assert not is_logged_in(client)
    html = response.content.decode()
    assert texts.LOGIN_FAILED in html
    # Mesma resposta para e-mail inexistente e senha errada; e-mail volta preenchido.
    assert parse_html(response).find("input", name="email").get("value") == email
    assert password not in html
    assert parse_html(response).find(role="alert") is not None


def test_inactive_account_cannot_login(client, seller):
    seller.user.is_active = False
    seller.user.save()
    response = login(client)
    assert texts.LOGIN_FAILED in response.content.decode()
    assert not is_logged_in(client)


def test_logged_in_get_redirects(seller_client):
    assert seller_client.get(URL)["Location"] == "/meus-anuncios/"


# Limite: 5 falhas em 15 min por IP e pelo par IP + e-mail; 50 por hora por e-mail ----


def test_five_failures_block_ip_even_with_right_password(client, seller):
    for _ in range(5):
        assert login(client, password="errada-123456").status_code == 200
    blocked = login(client)
    assert blocked.status_code == 429
    assert blocked["Retry-After"] == "900"
    assert texts.LOGIN_RATE_LIMITED in blocked.content.decode()
    assert not is_logged_in(client)
    assert_accessible_page(blocked)


def test_ip_limit_counts_different_emails(client, seller):
    for i in range(5):
        login(client, email=f"outra{i}@exemplo.test", password="x")
    assert login(client).status_code == 429


def test_pair_limit_blocks_one_email_from_one_ip(client, seller, monkeypatch):
    # Com o limite por IP folgado, o par IP + e-mail barra a 6ª tentativa na mesma conta.
    monkeypatch.setattr(views, "LOGIN_IP_LIMIT", 100)
    for _ in range(5):
        assert login(client, password="errada-123456").status_code == 200
    blocked = login(client, email=EMAIL.upper())
    assert blocked.status_code == 429
    assert blocked["Retry-After"] == "900"
    assert not is_logged_in(client)
    # O mesmo IP ainda tenta outra conta, e a dona da conta entra de outro IP.
    assert login(client, email="outra@exemplo.test", password="x").status_code == 200
    assert login(client, ip="10.0.0.2").status_code == 302


def test_failures_from_other_ips_do_not_lock_the_owner_out(client, seller):
    # S2: 5 falhas no início de cada janela, de outros IPs, não trancam a dona da conta.
    with time_machine.travel("2026-11-05 10:00:00-03:00", tick=False) as traveller:
        for window in range(3):
            for i in range(5):
                login(client, password="errada-123456", ip=f"10.1.{window}.{i}")
            assert login(client, ip="10.9.9.9").status_code == 302
            client.post("/sair/")
            traveller.shift(timedelta(minutes=15))


def test_email_limit_counts_different_ips_up_to_50_per_hour(client, seller):
    with time_machine.travel("2026-11-05 10:00:00-03:00", tick=False) as traveller:
        for i in range(50):
            login(client, password="errada-123456", ip=f"10.0.{i // 5}.{i % 5}")
        blocked = login(client, email=EMAIL.upper(), ip="10.0.200.1")
        assert blocked.status_code == 429
        assert blocked["Retry-After"] == "3600"
        assert not is_logged_in(client)
        # Outro e-mail, de um IP novo, não é afetado.
        other = login(client, email="outra@exemplo.test", password="x", ip="10.0.201.1")
        assert other.status_code == 200
        traveller.shift(timedelta(hours=1))
        assert login(client, ip="10.0.200.1").status_code == 302


def test_success_is_not_counted(client, seller):
    for _ in range(6):
        assert login(client).status_code == 302
        client.post("/sair/")


def test_block_ends_with_the_window(client, seller):
    with time_machine.travel("2026-11-05 10:00:00-03:00", tick=False) as traveller:
        for _ in range(5):
            login(client, password="errada-123456")
        assert login(client).status_code == 429
        traveller.shift(timedelta(minutes=15))
        assert login(client).status_code == 302


def test_counters_store_only_hashes(client, seller):
    login(client, password="errada-123456")
    rows = list(RateLimitCounter.objects.values_list("scope", "key_hash"))
    assert {scope for scope, _ in rows} == {"login_ip", "login_ip_email", "login_email"}
    for _, key_hash in rows:
        assert re.fullmatch(r"[0-9a-f]{64}", key_hash)
        assert "ana" not in key_hash


# Logout e CSRF ------------------------------------------------------------------


def test_logout_requires_post(seller_client):
    assert seller_client.get("/sair/").status_code == 405
    response = seller_client.post("/sair/")
    assert response.status_code == 302
    assert response["Location"] == "/"
    assert "_auth_user_id" not in seller_client.session


def test_login_csrf_required(seller):
    client = Client(enforce_csrf_checks=True)
    assert login(client).status_code == 403
    page = client.get(URL)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    response = login(client, csrfmiddlewaretoken=token.group(1))
    assert response.status_code == 302
