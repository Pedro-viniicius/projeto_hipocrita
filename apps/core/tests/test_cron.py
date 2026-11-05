"""Rota da limpeza agendada `/_tarefas/limpeza/` (Vercel Cron e GitHub Actions; CA5, CA6)."""

import hmac
from datetime import timedelta
from unittest import mock

import pytest
from django.core import checks
from django.urls import reverse
from django.utils import timezone

from apps.core.models import RateLimitCounter
from apps.core.testing import assert_no_set_cookie

pytestmark = pytest.mark.django_db

URL = "/_tarefas/limpeza/"
SECRET = "segredo-de-teste-0123456789abcdefghijklmnop"


@pytest.fixture
def cron_secret(settings):
    settings.CRON_SECRET = SECRET
    return SECRET


@pytest.fixture
def counters():
    """Um contador vencido (25 h) e um em uso (1 h)."""
    now = timezone.now()
    old = RateLimitCounter.objects.create(
        scope="login_ip", key_hash="a" * 64, window_start=now - timedelta(hours=25), count=1
    )
    fresh = RateLimitCounter.objects.create(
        scope="login_ip", key_hash="b" * 64, window_start=now - timedelta(hours=1), count=1
    )
    return old, fresh


def _remaining() -> set[str]:
    return set(RateLimitCounter.objects.values_list("key_hash", flat=True))


def test_route_name_and_path():
    assert reverse("core:cleanup_cron") == URL


@pytest.mark.parametrize("auth", [None, "Bearer ", "Bearer qualquer-coisa"])
def test_without_secret_configured_route_does_not_exist(client, settings, counters, auth):
    # "Bearer " é exatamente o que um segredo vazio esperaria: precisa dar 404.
    settings.CRON_SECRET = ""
    headers = {"authorization": auth} if auth is not None else {}
    response = client.get(URL, headers=headers)
    assert response.status_code == 404
    assert _remaining() == {"a" * 64, "b" * 64}


@pytest.mark.parametrize(
    "auth",
    [
        None,
        "",
        "Bearer errado",
        SECRET,  # sem o prefixo
        f"bearer {SECRET}",  # prefixo com outra caixa
        f"Bearer  {SECRET}",  # espaço a mais
        f"Bearer {SECRET} ",
        f"Bearer {SECRET[:-1]}",
        f"Bearer {SECRET}x",
        f"Basic {SECRET}",
        "Bearer çãé",  # fora do ASCII: 401, não 500
    ],
)
def test_wrong_or_missing_header_gets_401(client, cron_secret, counters, auth):
    headers = {"authorization": auth} if auth is not None else {}
    response = client.get(URL, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "no-store" in response.headers["Cache-Control"]
    assert SECRET.encode() not in response.content
    # Nada foi apagado.
    assert _remaining() == {"a" * 64, "b" * 64}


def test_right_header_runs_cleanup(client, cron_secret, counters):
    response = client.get(URL, headers={"authorization": f"Bearer {SECRET}"})
    assert response.status_code == 200
    assert response.content == b"ok"  # sem contagens nem o que foi apagado
    assert response.headers["Content-Type"].startswith("text/plain")
    assert "no-store" in response.headers["Cache-Control"]
    assert_no_set_cookie(response)
    assert _remaining() == {"b" * 64}


def test_secret_is_compared_in_constant_time(client, cron_secret):
    with mock.patch("apps.core.views.hmac.compare_digest", wraps=hmac.compare_digest) as spy:
        response = client.get(URL, headers={"authorization": f"Bearer {SECRET}"})
    assert response.status_code == 200
    spy.assert_called_once_with(f"Bearer {SECRET}".encode(), f"Bearer {SECRET}".encode())


def test_repeated_calls_are_harmless(client, cron_secret, counters):
    headers = {"authorization": f"Bearer {SECRET}"}
    assert client.get(URL, headers=headers).status_code == 200
    assert client.get(URL, headers=headers).status_code == 200
    assert _remaining() == {"b" * 64}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete", "head"])
def test_other_methods_get_405_and_do_nothing(client, cron_secret, counters, method):
    response = getattr(client, method)(URL, headers={"authorization": f"Bearer {SECRET}"})
    assert response.status_code == 405
    assert _remaining() == {"a" * 64, "b" * 64}


# System check do formato do segredo (S4, Q1) --------------------------------------


def _cron_secret_warnings(deploy: bool = True):
    found = checks.run_checks(include_deployment_checks=deploy)
    return [m for m in found if m.id == "core.W002"]


@pytest.mark.parametrize(
    "secret",
    [
        "",  # rota desligada: nada a avisar
        SECRET,
        "a" * 32,  # exatamente o mínimo
        "Ab0._~+/=-" * 4,  # todos os caracteres aceitos
        "Zx3Kq9_tL-0aBcDeFgHiJkLmNoPqRsTuVwXyZ01234",  # token_urlsafe(32): 43 caracteres
    ],
)
def test_deploy_check_quiet_with_a_good_or_empty_secret(settings, secret):
    settings.CRON_SECRET = secret
    assert _cron_secret_warnings() == []


@pytest.mark.parametrize(
    "secret",
    [
        "a" * 31,  # curto
        "curto",
        "segredo com espaço 0123456789abcdefghij",
        "sëgredo-çã-0123456789abcdefghijklmnopq",  # fora do ASCII
        "segredo:0123456789abcdefghijklmnopqrstu",
        "segredo,0123456789abcdefghijklmnopqrstu",
        "segredo\n0123456789abcdefghijklmnopqrstu",
    ],
)
def test_deploy_check_warns_about_short_or_odd_secret_without_showing_it(settings, secret):
    settings.CRON_SECRET = secret
    (warning,) = _cron_secret_warnings()
    assert "32 caracteres" in warning.msg
    assert "token_urlsafe" in warning.hint
    assert secret not in warning.msg + warning.hint


def test_cron_secret_check_only_runs_with_deploy(settings):
    settings.CRON_SECRET = "curto"
    assert _cron_secret_warnings(deploy=False) == []
