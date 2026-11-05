"""R18: nenhum contador com dado pessoal passa de 24 h; o teto diário de cadastros não reabre.

A página de privacidade promete "em até 24 horas" para o código (HMAC) do IP, do e-mail ou do
usuário. `purge_old` apaga pelo `window_start` (início da janela), e o cron do `cleanup_data`
roda de hora em hora (README). O pior caso é a linha criada logo no início da janela.
"""

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
import time_machine
from django.core.management import call_command
from django.test import Client

from apps.accounts import views as accounts_views
from apps.accounts.models import User
from apps.catalog import services_seller, views_public
from apps.core import ratelimit
from apps.core.models import RateLimitCounter
from apps.moderation import views_public as moderation_views
from texts import accounts as texts

pytestmark = pytest.mark.django_db

# 10h UTC: início de janela para todas as janelas de 15 min e de 1 h.
T0 = datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC)
PERSONAL_KEY = ratelimit.email_key("pessoa@exemplo.test")
DAY = timedelta(hours=24)

# (escopo, janela em segundos): todos guardam HMAC de IP, e-mail ou usuário.
PERSONAL_SCOPES = [
    (accounts_views.SCOPE_LOGIN_IP, accounts_views.LOGIN_IP_WINDOW_S),
    (accounts_views.SCOPE_LOGIN_PAIR, accounts_views.LOGIN_PAIR_WINDOW_S),
    (accounts_views.SCOPE_LOGIN_EMAIL, accounts_views.LOGIN_EMAIL_WINDOW_S),
    (accounts_views.SCOPE_SIGNUP, accounts_views.SIGNUP_WINDOW_S),
    (accounts_views.SCOPE_RESET, accounts_views.RESET_WINDOW_S),
    (accounts_views.SCOPE_DELETE, accounts_views.DELETE_WINDOW_S),
    ("whatsapp", views_public.WHATSAPP_RATE_WINDOW_S),
    (services_seller.PHOTOS_SCOPE, services_seller.PHOTOS_WINDOW_S),
    (moderation_views.SCOPE_REPORT, moderation_views.REPORT_WINDOW_S),
]
IDS = [scope for scope, _ in PERSONAL_SCOPES]


def cleanup_at(moment: datetime) -> None:
    with time_machine.travel(moment, tick=False):
        call_command("cleanup_data", stdout=StringIO())


def row_exists(scope: str) -> bool:
    return RateLimitCounter.objects.filter(scope=scope, key_hash=PERSONAL_KEY).exists()


def create_row(scope: str, window_s: int, created_at: datetime) -> None:
    ratelimit.register(scope, PERSONAL_KEY, window_s, now=created_at)
    assert row_exists(scope)


@pytest.mark.parametrize(("scope", "window_s"), PERSONAL_SCOPES, ids=IDS)
@pytest.mark.parametrize("into_window", ["inicio", "fim"])
def test_personal_row_is_gone_after_23h_and_1min(scope, window_s, into_window):
    created = T0 if into_window == "inicio" else T0 + timedelta(seconds=window_s - 1)
    create_row(scope, window_s, created)
    cleanup_at(created + timedelta(hours=23, minutes=1))
    assert not row_exists(scope)


@pytest.mark.parametrize(("scope", "window_s"), PERSONAL_SCOPES, ids=IDS)
@pytest.mark.parametrize("cron_minute", [7, 59])
def test_hourly_cron_never_keeps_personal_row_past_24h(scope, window_s, cron_minute):
    # Cron de hora em hora, sem tráfego: o primeiro `cleanup_data` depois de T + 24 h tem de
    # encontrar a linha já apagada, ou seja, a última rodada antes de T + 24 h a apagou.
    create_row(scope, window_s, T0)
    first_run = T0.replace(minute=cron_minute) + timedelta(hours=22)
    gone_at = None
    for hour in range(6):
        run_at = first_run + timedelta(hours=hour)
        cleanup_at(run_at)
        if not row_exists(scope):
            gone_at = run_at
            break
    assert gone_at is not None
    assert gone_at - T0 <= DAY, f"dado pessoal ficou {gone_at - T0} (prometido: até 24 h)"


def test_recent_personal_row_is_kept():
    # Contraponto: a limpeza não pode apagar o contador ainda dentro da janela de proteção.
    create_row("login_ip", 15 * 60, T0)
    cleanup_at(T0 + timedelta(hours=2))
    assert row_exists("login_ip")


# CA3: o teto diário (chave global, sem dado pessoal) vale até o fim da janela de 24 h ---------


def _signup(email: str, ip: str):
    return Client().post(
        "/cadastrar/",
        {
            "display_name": "Doces da Ana",
            "email": email,
            "password": "pao-de-queijo-quentinho",
            "whatsapp": "(35) 91234-5678",
        },
        REMOTE_ADDR=ip,
    )


def _fill_daily_cap(settings):
    settings.SIGNUPS_PER_DAY = 2
    with time_machine.travel(datetime(2026, 11, 5, 9, 0, 0, tzinfo=UTC), tick=False):
        for i in range(2):
            assert _signup(f"teto{i}@exemplo.test", f"10.9.0.{i}").status_code == 302
    assert User.objects.count() == 2


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 5, 23, 30, 0, tzinfo=UTC),
        datetime(2026, 11, 5, 23, 59, 30, tzinfo=UTC),
    ],
    ids=["meio", "perto-do-fim", "ultimo-minuto"],
)
def test_cleanup_does_not_reopen_the_daily_signup_cap(settings, moment):
    _fill_daily_cap(settings)
    cleanup_at(moment)
    with time_machine.travel(moment + timedelta(seconds=1), tick=False):
        page = Client().get("/cadastrar/")
        assert texts.SIGNUP_DAILY_LIMIT in page.content.decode()
        assert _signup("atrasada@exemplo.test", "10.9.9.9").status_code == 429
    assert User.objects.count() == 2
    assert RateLimitCounter.objects.filter(scope=accounts_views.SCOPE_SIGNUP_DAY).exists()


def test_daily_signup_cap_reopens_after_the_window_even_with_cleanup(settings):
    _fill_daily_cap(settings)
    cleanup_at(datetime(2026, 11, 6, 0, 1, 0, tzinfo=UTC))
    with time_machine.travel(datetime(2026, 11, 6, 0, 2, 0, tzinfo=UTC), tick=False):
        assert _signup("nova@exemplo.test", "10.9.9.8").status_code == 302
