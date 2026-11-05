"""Limite de tentativas sobre o próprio banco (sem Redis).

Janelas fixas: a contagem vale de `window_start` até `window_start + window_s`.
As chaves são sempre HMAC-SHA256 (com a SECRET_KEY) do IP, do usuário ou do
e-mail: o valor puro nunca é gravado.

Limpeza (a cada gravação e pelo comando `cleanup_data`, de hora em hora), contada do
início da janela:
- contadores com dado pessoal (HMAC de IP, e-mail ou usuário) saem com
  `retention.RATE_LIMIT_PURGE_HOURS` (23 h), para que nenhum passe das 24 h prometidas
  na página de privacidade mesmo sem tráfego. Por isso a janela deles vai até 23 h;
- contadores do site inteiro (`SITE_WIDE_SCOPES`, só aceitam `global_key(scope)`, sem
  dado pessoal) ficam até a janela de 24 h acabar, senão a limpeza reabriria o teto
  antes da hora.

IPv6 conta pela rede /64: um mesmo cliente costuma ter a /64 inteira e
trocaria de endereço a cada tentativa.

Uso típico:
- decorador `rate_limited("signup", 5, 3600)` conta cada POST e responde 429;
- login: `is_blocked(...)` antes de autenticar e `register(...)` só na falha,
  por IP (`client_key`), pelo par IP + e-mail (`pair_key`) e por e-mail (`email_key`);
- teto do site inteiro (cadastros por dia): escopo em `SITE_WIDE_SCOPES` com a
  chave `global_key(scope)`;
- fotos: `register("photos", user_key(request), 3600, amount=len(files))`.
"""

import ipaddress
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from functools import wraps

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.crypto import salted_hmac

from apps.core import clock, retention
from apps.core.models import RateLimitCounter
from texts import common as texts

MAX_WINDOW_S = 24 * 60 * 60
# Contadores com dado pessoal: apagados antes do prazo prometido (ver `retention`).
RETENTION = timedelta(hours=retention.RATE_LIMIT_PURGE_HOURS)
PERSONAL_MAX_WINDOW_S = int(RETENTION.total_seconds())
# Limites do site inteiro: a chave é fixa (`global_key(scope)`), sem dado pessoal, e o
# contador fica até a janela acabar.
SITE_WIDE_SCOPES = frozenset({"signup_day"})
SITE_WIDE_RETENTION = timedelta(seconds=MAX_WINDOW_S)
_SCOPE_MAX = RateLimitCounter._meta.get_field("scope").max_length
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _hmac(kind: str, value: str) -> str:
    return salted_hmac(f"apps.core.ratelimit.{kind}", value, algorithm="sha256").hexdigest()


def client_ip(request: HttpRequest) -> str:
    """IP do cliente. Usa `X-Forwarded-For` só com `TRUSTED_PROXY_HOPS > 0`.

    Com N proxies confiáveis, o IP real é o N-ésimo a partir da direita do
    cabeçalho (cada proxy acrescenta quem o chamou). Se o cabeçalho tiver menos
    entradas do que o esperado, volta para `REMOTE_ADDR`, que não é forjável.
    """
    remote = request.META.get("REMOTE_ADDR", "") or ""
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        raw = request.META.get("HTTP_X_FORWARDED_FOR", "")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return remote


def ip_bucket(ip: str) -> str:
    """O que identifica o cliente no limite: IPv4 inteiro ou a rede /64 do IPv6.

    IPv6 com IPv4 embutido (`::ffff:1.2.3.4`) vale como o IPv4. Texto que não é
    IP (proxy mal configurado) é usado como veio, só sem espaços.
    """
    raw = ip.strip()
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        prefix = int(addr) >> 64 << 64  # descarta também o "%zona"
        return str(ipaddress.IPv6Network((prefix, 64)))
    return str(addr)


def client_key(request: HttpRequest) -> str:
    """HMAC do IP do cliente (a rede /64, no IPv6)."""
    return _hmac("ip", ip_bucket(client_ip(request)))


def user_key(request: HttpRequest) -> str:
    """HMAC do id do usuário logado; para anônimo, cai no IP."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return _hmac("user", str(user.pk))
    return client_key(request)


def email_key(email: str) -> str:
    """HMAC do e-mail normalizado (sem espaços, minúsculo)."""
    return _hmac("email", email.strip().lower())


def pair_key(request: HttpRequest, email: str) -> str:
    """HMAC do par IP do cliente + e-mail normalizado."""
    return _hmac("ip_email", f"{ip_bucket(client_ip(request))}|{email.strip().lower()}")


def global_key(name: str) -> str:
    """HMAC fixo para um limite do site inteiro (ex.: cadastros por dia)."""
    return _hmac("global", name)


def window_start(now: datetime, window_s: int) -> datetime:
    ts = int(now.timestamp())
    return datetime.fromtimestamp(ts - ts % window_s, tz=UTC)


def _check(scope: str, key: str, window_s: int) -> None:
    if not scope or len(scope) > _SCOPE_MAX:
        raise ValueError(f"scope deve ter de 1 a {_SCOPE_MAX} caracteres.")
    if not _HASH_RE.match(key):
        raise ValueError("key deve vir de uma das funções *_key deste módulo (HMAC).")
    if not 0 < window_s <= MAX_WINDOW_S:
        raise ValueError("window_s deve estar entre 1 s e 24 h.")
    if scope in SITE_WIDE_SCOPES:
        # Senão um HMAC pessoal ficaria guardado pelo prazo maior.
        if key != global_key(scope):
            raise ValueError("Escopo do site inteiro só aceita global_key(scope).")
    elif window_s > PERSONAL_MAX_WINDOW_S:
        # A limpeza apagaria o contador antes de a janela acabar.
        raise ValueError(
            f"window_s de contador com dado pessoal deve ser de até "
            f"{retention.RATE_LIMIT_PURGE_HOURS} h."
        )


def is_blocked(
    scope: str, key: str, limit: int, window_s: int, now: datetime | None = None
) -> bool:
    """True se a chave já fez `limit` registros ou mais na janela atual."""
    _check(scope, key, window_s)
    now = now or clock.now()
    count = (
        RateLimitCounter.objects.filter(
            scope=scope, key_hash=key, window_start=window_start(now, window_s)
        )
        .values_list("count", flat=True)
        .first()
    )
    return (count or 0) >= limit


def register(
    scope: str, key: str, window_s: int, now: datetime | None = None, *, amount: int = 1
) -> None:
    """Soma `amount` à janela atual da chave e apaga os contadores vencidos (`purge_old`)."""
    _check(scope, key, window_s)
    if amount < 1:
        raise ValueError("amount deve ser positivo.")
    now = now or clock.now()
    start = window_start(now, window_s)
    rows = RateLimitCounter.objects.filter(scope=scope, key_hash=key, window_start=start)
    if not rows.update(count=F("count") + amount):
        try:
            with transaction.atomic():
                RateLimitCounter.objects.create(
                    scope=scope, key_hash=key, window_start=start, count=amount
                )
        except IntegrityError:
            # Outra requisição criou a linha ao mesmo tempo.
            rows.update(count=F("count") + amount)
    purge_old(now)


def purge_old(now: datetime | None = None) -> int:
    """Apaga os contadores vencidos. Devolve quantos apagou.

    Com dado pessoal: janela iniciada há mais de `RETENTION` (23 h). Do site inteiro:
    há mais de `SITE_WIDE_RETENTION` (24 h), quando a janela já acabou.
    """
    now = now or clock.now()
    site_wide = Q(scope__in=SITE_WIDE_SCOPES)
    expired = (~site_wide & Q(window_start__lt=now - RETENTION)) | (
        site_wide & Q(window_start__lt=now - SITE_WIDE_RETENTION)
    )
    deleted, _ = RateLimitCounter.objects.filter(expired).delete()
    return deleted


def too_many_requests(request: HttpRequest, retry_after_s: int) -> HttpResponse:
    """Resposta 429 com a página `errors/429.html`."""
    response = render(
        request,
        "errors/429.html",
        {"title": texts.RATE_LIMITED_TITLE, "message": texts.RATE_LIMITED_TEXT},
        status=429,
    )
    response["Retry-After"] = str(retry_after_s)
    return response


def rate_limited(
    scope: str,
    limit: int,
    window_s: int,
    key: str = "ip",
    methods: Iterable[str] = ("POST",),
) -> Callable:
    """Decorador: conta cada requisição dos `methods` e responde 429 ao passar de `limit`."""
    if key not in {"ip", "user"}:
        raise ValueError('key deve ser "ip" ou "user".')
    methods = {m.upper() for m in methods}

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if request.method in methods:
                k = client_key(request) if key == "ip" else user_key(request)
                if is_blocked(scope, k, limit, window_s):
                    return too_many_requests(request, window_s)
                register(scope, k, window_s)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
