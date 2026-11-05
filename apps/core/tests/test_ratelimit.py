"""Limite de tentativas (CA14): HMAC, janelas, limpeza dos vencidos e resposta 429."""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts import views as accounts_views
from apps.core import ratelimit
from apps.core.models import RateLimitCounter

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 5, 15, 0, 0, tzinfo=UTC)
rf = RequestFactory()


def _request(ip="203.0.113.5", xff=None, method="post"):
    extra = {"REMOTE_ADDR": ip}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    request = getattr(rf, method)("/x/", **extra)
    request.user = AnonymousUser()
    return request


# Chaves -----------------------------------------------------------------------


def test_client_key_is_hmac_not_ip():
    key = ratelimit.client_key(_request("203.0.113.5"))
    assert len(key) == 64
    assert "203.0.113.5" not in key
    assert key == ratelimit.client_key(_request("203.0.113.5"))
    assert key != ratelimit.client_key(_request("203.0.113.6"))


def test_xff_ignored_without_trusted_proxy(settings):
    settings.TRUSTED_PROXY_HOPS = 0
    assert ratelimit.client_ip(_request("10.0.0.1", xff="1.2.3.4")) == "10.0.0.1"


@pytest.mark.parametrize(
    ("hops", "xff", "expected"),
    [
        (1, "6.6.6.6, 198.51.100.7", "198.51.100.7"),  # cliente forjou a 1ª entrada
        (2, "6.6.6.6, 198.51.100.7, 172.16.0.2", "198.51.100.7"),
        (2, "198.51.100.7", "10.0.0.1"),  # menos entradas que o esperado: REMOTE_ADDR
        (1, "", "10.0.0.1"),
    ],
)
def test_xff_with_trusted_proxies(settings, hops, xff, expected):
    settings.TRUSTED_PROXY_HOPS = hops
    assert ratelimit.client_ip(_request("10.0.0.1", xff=xff)) == expected


# IPv6: um cliente costuma ter uma rede /64 inteira (S5) ------------------------


def test_ipv6_same_64_shares_key():
    a = ratelimit.client_key(_request("2001:db8:1:2:aaaa::1"))
    b = ratelimit.client_key(_request("2001:db8:1:2:ffff:ffff:ffff:ffff"))
    other_net = ratelimit.client_key(_request("2001:db8:1:3::1"))
    assert a == b
    assert a != other_net


def test_ipv6_notation_is_normalized():
    assert ratelimit.client_key(_request("2001:DB8:0:0::1")) == ratelimit.client_key(
        _request("2001:db8::9")
    )


def test_ipv4_mapped_ipv6_counts_as_ipv4():
    mapped = ratelimit.client_key(_request("::ffff:203.0.113.5"))
    assert mapped == ratelimit.client_key(_request("203.0.113.5"))
    assert mapped != ratelimit.client_key(_request("::ffff:203.0.113.6"))


def test_ipv6_from_trusted_proxy_header(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    a = ratelimit.client_key(_request("10.0.0.1", xff="2001:db8:5:6::1"))
    b = ratelimit.client_key(_request("10.0.0.1", xff="2001:db8:5:6::abcd"))
    assert a == b
    assert a != ratelimit.client_key(_request("10.0.0.1", xff="2001:db8:5:7::1"))


@pytest.mark.parametrize("ip", ["fe80::1%eth0", "nao-e-ip", "", "999.1.1.1"])
def test_odd_addresses_still_give_a_hash(ip):
    key = ratelimit.client_key(_request(ip))
    assert len(key) == 64
    assert ip == "" or ip not in key


def test_ip_bucket():
    assert ratelimit.ip_bucket("203.0.113.5") == "203.0.113.5"
    assert ratelimit.ip_bucket("::ffff:203.0.113.5") == "203.0.113.5"
    assert ratelimit.ip_bucket("2001:db8:1:2:3:4:5:6") == "2001:db8:1:2::/64"
    assert ratelimit.ip_bucket("fe80::1%eth0") == "fe80::/64"
    assert ratelimit.ip_bucket(" nao-e-ip ") == "nao-e-ip"


def test_pair_key_joins_ip_and_email():
    key = ratelimit.pair_key(_request("203.0.113.5"), " Ana@Exemplo.TEST ")
    assert key == ratelimit.pair_key(_request("203.0.113.5"), "ana@exemplo.test")
    assert len(key) == 64 and "ana" not in key
    assert key != ratelimit.pair_key(_request("203.0.113.6"), "ana@exemplo.test")
    assert key != ratelimit.pair_key(_request("203.0.113.5"), "bia@exemplo.test")
    assert key != ratelimit.email_key("ana@exemplo.test")
    assert key != ratelimit.client_key(_request("203.0.113.5"))
    # Mesma rede /64 conta como o mesmo cliente.
    v6 = ratelimit.pair_key(_request("2001:db8::1"), "ana@exemplo.test")
    assert v6 == ratelimit.pair_key(_request("2001:db8::2"), "ana@exemplo.test")


def test_global_key_is_fixed_hmac():
    key = ratelimit.global_key("signup")
    assert key == ratelimit.global_key("signup")
    assert key != ratelimit.global_key("outra")
    assert len(key) == 64


def test_email_key_normalizes():
    assert ratelimit.email_key(" Ana@Exemplo.TEST ") == ratelimit.email_key("ana@exemplo.test")
    assert "ana" not in ratelimit.email_key("ana@exemplo.test")


def test_user_key_differs_from_ip_key(make_user):
    request = _request()
    anon_key = ratelimit.user_key(request)
    assert anon_key == ratelimit.client_key(request)
    request.user = make_user()
    assert ratelimit.user_key(request) != anon_key


# Contagem ---------------------------------------------------------------------


def test_blocks_after_limit_and_resets_next_window():
    key = ratelimit.client_key(_request())
    for _ in range(5):
        assert not ratelimit.is_blocked("login", key, 5, 900, now=NOW)
        ratelimit.register("login", key, 900, now=NOW)
    assert ratelimit.is_blocked("login", key, 5, 900, now=NOW)
    # Outro escopo e outra chave não são afetados.
    assert not ratelimit.is_blocked("signup", key, 5, 900, now=NOW)
    other = ratelimit.client_key(_request("198.51.100.1"))
    assert not ratelimit.is_blocked("login", other, 5, 900, now=NOW)
    # Próxima janela de 15 min zera.
    assert not ratelimit.is_blocked("login", key, 5, 900, now=NOW + timedelta(minutes=15))


def test_register_amount_counts_files():
    key = ratelimit.client_key(_request())
    ratelimit.register("photos", key, 3600, now=NOW, amount=19)
    assert not ratelimit.is_blocked("photos", key, 20, 3600, now=NOW)
    ratelimit.register("photos", key, 3600, now=NOW, amount=1)
    assert ratelimit.is_blocked("photos", key, 20, 3600, now=NOW)


def test_stores_only_hash_and_purges_expired():
    key = ratelimit.client_key(_request("203.0.113.5"))
    ratelimit.register("report", key, 3600, now=NOW)
    row = RateLimitCounter.objects.get()
    assert row.key_hash == key
    assert "203.0.113.5" not in str(list(RateLimitCounter.objects.values()))
    ratelimit.register("report", key, 3600, now=NOW + timedelta(hours=25))
    starts = list(RateLimitCounter.objects.values_list("window_start", flat=True))
    assert starts == [ratelimit.window_start(NOW + timedelta(hours=25), 3600)]


@pytest.mark.parametrize(
    ("scope", "key", "window"),
    [
        ("login", "203.0.113.5", 900),  # valor puro, sem HMAC
        ("x" * 21, "a" * 64, 900),
        ("", "a" * 64, 900),
        ("login", "a" * 64, 0),
        ("login", "a" * 64, 2 * 86400),
    ],
)
def test_rejects_invalid_arguments(scope, key, window):
    with pytest.raises(ValueError):
        ratelimit.register(scope, key, window, now=NOW)


def test_personal_window_must_fit_in_the_purge_retention():
    # R18: a limpeza apaga o contador pessoal com 23 h; janela maior seria cortada no meio.
    key = ratelimit.email_key("ana@exemplo.test")
    with pytest.raises(ValueError):
        ratelimit.register("login", key, ratelimit.PERSONAL_MAX_WINDOW_S + 1, now=NOW)
    ratelimit.register("login", key, ratelimit.PERSONAL_MAX_WINDOW_S, now=NOW)
    assert ratelimit.is_blocked("login", key, 1, ratelimit.PERSONAL_MAX_WINDOW_S, now=NOW)


def test_site_wide_scope_only_takes_its_global_key():
    # O escopo do site inteiro fica 24 h: não pode guardar HMAC de IP, e-mail ou usuário.
    scope = accounts_views.SCOPE_SIGNUP_DAY
    assert scope in ratelimit.SITE_WIDE_SCOPES
    for key in (ratelimit.client_key(_request()), ratelimit.global_key("outro")):
        with pytest.raises(ValueError):
            ratelimit.register(scope, key, 24 * 3600, now=NOW)
    ratelimit.register(scope, ratelimit.global_key(scope), 24 * 3600, now=NOW)
    assert RateLimitCounter.objects.filter(scope=scope).count() == 1


def test_purge_keeps_site_wide_counter_until_its_window_ends():
    personal = ratelimit.client_key(_request())
    site = ratelimit.global_key(accounts_views.SCOPE_SIGNUP_DAY)
    start = ratelimit.window_start(NOW, 24 * 3600)
    ratelimit.register("login", personal, 3600, now=start)
    ratelimit.register(accounts_views.SCOPE_SIGNUP_DAY, site, 24 * 3600, now=start)
    assert ratelimit.purge_old(start + timedelta(hours=23, minutes=1)) == 1
    assert list(RateLimitCounter.objects.values_list("scope", flat=True)) == ["signup_day"]
    assert ratelimit.purge_old(start + timedelta(hours=24, minutes=1)) == 1
    assert not RateLimitCounter.objects.exists()


# Decorador --------------------------------------------------------------------


def _view(request):
    return HttpResponse("ok")


def test_decorator_returns_429_after_limit():
    view = ratelimit.rate_limited("signup", 2, 3600)(_view)
    assert view(_request()).status_code == 200
    assert view(_request()).status_code == 200
    blocked = view(_request())
    assert blocked.status_code == 429
    assert blocked["Retry-After"] == "3600"
    assert b"Muitas tentativas" in blocked.content
    # GET não conta nem é bloqueado.
    assert view(_request(method="get")).status_code == 200


def test_decorator_by_user(make_user):
    view = ratelimit.rate_limited("photos", 1, 3600, key="user")(_view)
    first = _request()
    first.user = make_user()
    assert view(first).status_code == 200
    assert view(first).status_code == 429
    second = _request()
    second.user = make_user()
    assert view(second).status_code == 200


def test_decorator_rejects_unknown_key():
    with pytest.raises(ValueError):
        ratelimit.rate_limited("x", 1, 60, key="email")
