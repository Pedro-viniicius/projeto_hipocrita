"""Contas: cadastro, login, senha e exclusão de conta.

Limites de tentativas (`apps/core/ratelimit.py`, só HMAC no banco):
- login: 5 falhas em 15 min por IP, 5 falhas em 15 min pelo par IP + e-mail e
  50 falhas por hora por e-mail (só contra ataque espalhado em muitos IPs).
  Bloqueado, nem a senha certa entra até a janela virar. Não há bloqueio de
  5 falhas só por e-mail: quem tenta de outro IP não tranca a dona da conta;
- cadastro: 5 envios por hora por IP e, no site inteiro, `SIGNUPS_PER_DAY`
  contas novas por dia (só conta conta criada, não envio com erro). Com
  `SIGNUPS_PER_DAY=0` o cadastro fica fechado, sem prazo para reabrir, e os
  envios nem passam pelo limite por IP (nada é gravado);
- recuperação de senha: 5 envios por hora por IP;
- exclusão de conta: 5 senhas erradas em 15 min por usuário.

Recuperação de senha só funciona com e-mail de verdade (ou com DEBUG=true): com
o backend de console em produção, o link com o token iria para o log, então as
páginas mostram o contato da administração, se houver (`password_reset_enabled`).

Nada aqui registra e-mail, telefone ou senha em log.
"""

from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import (
    ChangePasswordForm,
    DeleteAccountForm,
    LoginForm,
    NewPasswordForm,
    ResetRequestForm,
    SignupForm,
)
from apps.core import clock, ratelimit
from texts import accounts as texts

LOGIN_IP_LIMIT = 5
LOGIN_IP_WINDOW_S = 15 * 60
LOGIN_PAIR_LIMIT = 5
LOGIN_PAIR_WINDOW_S = 15 * 60
LOGIN_EMAIL_LIMIT = 50
LOGIN_EMAIL_WINDOW_S = 60 * 60
SIGNUP_LIMIT = 5
SIGNUP_WINDOW_S = 60 * 60
SIGNUP_DAY_WINDOW_S = 24 * 60 * 60  # vira à meia-noite UTC
RESET_LIMIT = 5
RESET_WINDOW_S = 60 * 60
DELETE_LIMIT = 5
DELETE_WINDOW_S = 15 * 60

SCOPE_LOGIN_IP = "login_ip"
SCOPE_LOGIN_PAIR = "login_ip_email"
SCOPE_LOGIN_EMAIL = "login_email"
SCOPE_SIGNUP = "signup"
SCOPE_SIGNUP_DAY = "signup_day"
SCOPE_RESET = "password_reset"
SCOPE_DELETE = "account_delete"

CONSOLE_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


def _has_seller(user) -> bool:
    try:
        user.seller  # noqa: B018  (só confere se o perfil existe)
    except ObjectDoesNotExist:
        return False
    return True


def _home_for(user) -> str:
    """Destino depois de entrar: área do vendedor, ou administração para admin sem perfil."""
    if user.is_staff and not _has_seller(user):
        return reverse("moderation:approvals")
    return reverse("seller:dashboard")


def _profile_url(user) -> str:
    """Página de onde se chega à troca de senha e à exclusão de conta."""
    return reverse("seller:profile" if _has_seller(user) else "moderation:approvals")


def _safe_next(request: HttpRequest) -> str | None:
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return None


# Cadastro ---------------------------------------------------------------------


def _signups_closed() -> bool:
    """True com `SIGNUPS_PER_DAY=0`: cadastro fechado, sem data para reabrir."""
    return settings.SIGNUPS_PER_DAY == 0


def _signups_closed_for_today() -> bool:
    """True se o site já criou `SIGNUPS_PER_DAY` contas na janela de hoje (UTC)."""
    return ratelimit.is_blocked(
        SCOPE_SIGNUP_DAY,
        ratelimit.global_key(SCOPE_SIGNUP_DAY),
        settings.SIGNUPS_PER_DAY,
        SIGNUP_DAY_WINDOW_S,
    )


def _seconds_until_signups_reopen() -> int:
    now = clock.now()
    reopen = ratelimit.window_start(now, SIGNUP_DAY_WINDOW_S) + timedelta(
        seconds=SIGNUP_DAY_WINDOW_S
    )
    return max(1, int((reopen - now).total_seconds()))


def _signup_limit_response(request: HttpRequest, closed: bool) -> HttpResponse:
    """Aviso de cadastro fechado ou de teto do dia, sem formulário; POST dá 429."""
    context = {
        "limit_message": texts.SIGNUP_CLOSED if closed else texts.SIGNUP_DAILY_LIMIT,
        "signups_closed": closed,
        "contact_email": settings.PRIVACY_CONTACT_EMAIL,
    }
    if request.method != "POST":
        return render(request, "accounts/signup.html", context)
    response = render(request, "accounts/signup.html", context, status=429)
    if not closed:
        # Fechado não tem hora para reabrir: Retry-After seria promessa falsa.
        response["Retry-After"] = str(_seconds_until_signups_reopen())
    return response


def _answer_when_signups_closed(view):
    """Com o cadastro fechado, responde antes do limite por IP.

    Assim o 429 genérico do limitador ("tente de novo", `Retry-After`) nunca
    aparece no lugar do aviso de fechado, e o envio não grava o código do IP.
    Quem já entrou segue para a view (que o leva à área dele).
    """

    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if _signups_closed() and not request.user.is_authenticated:
            return _signup_limit_response(request, closed=True)
        return view(request, *args, **kwargs)

    return wrapped


@sensitive_post_parameters("password", "whatsapp")
@never_cache
@require_http_methods(["GET", "POST"])
@_answer_when_signups_closed
@ratelimit.rate_limited(SCOPE_SIGNUP, SIGNUP_LIMIT, SIGNUP_WINDOW_S)
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(_home_for(request.user))
    closed = _signups_closed()  # já tratado no decorador; aqui só por defesa
    if closed or _signups_closed_for_today():
        return _signup_limit_response(request, closed)
    form = SignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user is not None:
            ratelimit.register(
                SCOPE_SIGNUP_DAY, ratelimit.global_key(SCOPE_SIGNUP_DAY), SIGNUP_DAY_WINDOW_S
            )
            auth.login(request, user)
            messages.success(request, texts.SIGNUP_OK)
            return redirect("seller:dashboard")
    return render(request, "accounts/signup.html", {"form": form})


# Login e logout ---------------------------------------------------------------


def _login_limits(request: HttpRequest, raw_email: str) -> list[tuple[str, str, int, int]]:
    """(escopo, chave, limite, janela) que valem para esta tentativa de login."""
    limits = [(SCOPE_LOGIN_IP, ratelimit.client_key(request), LOGIN_IP_LIMIT, LOGIN_IP_WINDOW_S)]
    if raw_email:
        limits += [
            (
                SCOPE_LOGIN_PAIR,
                ratelimit.pair_key(request, raw_email),
                LOGIN_PAIR_LIMIT,
                LOGIN_PAIR_WINDOW_S,
            ),
            (
                SCOPE_LOGIN_EMAIL,
                ratelimit.email_key(raw_email),
                LOGIN_EMAIL_LIMIT,
                LOGIN_EMAIL_WINDOW_S,
            ),
        ]
    return limits


def _login_blocked_for(limits: list[tuple[str, str, int, int]]) -> int | None:
    """Janela (em segundos) do primeiro limite estourado, ou None se pode tentar."""
    for scope, key, limit, window_s in limits:
        if ratelimit.is_blocked(scope, key, limit, window_s):
            return window_s
    return None


def _register_login_failure(limits: list[tuple[str, str, int, int]]) -> None:
    for scope, key, _limit, window_s in limits:
        ratelimit.register(scope, key, window_s)


def password_reset_enabled() -> bool:
    """Recuperação de senha ligada: com DEBUG ou com um backend que envia de verdade.

    Com DEBUG=false e o backend de console (padrão sem SMTP), o e-mail com o link
    e o token iria para o log do servidor; nesse caso o fluxo fica desligado.
    """
    return settings.DEBUG or settings.EMAIL_BACKEND != CONSOLE_EMAIL_BACKEND


@sensitive_post_parameters("password")
@never_cache
@require_http_methods(["GET", "POST"])
def login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and request.method == "GET":
        return redirect(_safe_next(request) or _home_for(request.user))
    context = {
        "next": _safe_next(request) or "",
        "reset_enabled": password_reset_enabled(),
        "contact_email": settings.PRIVACY_CONTACT_EMAIL,
    }
    if request.method != "POST":
        context["form"] = LoginForm(request)
        return render(request, "accounts/login.html", context)

    raw_email = (request.POST.get("email") or "").strip()
    limits = _login_limits(request, raw_email)
    retry_after = _login_blocked_for(limits)
    if retry_after is not None:
        # Mostra o formulário com o e-mail digitado, sem tentar autenticar.
        form = LoginForm(request, initial={"email": raw_email[:254]})
        context.update(form=form, rate_limited=True, limit_message=texts.LOGIN_RATE_LIMITED)
        response = render(request, "accounts/login.html", context, status=429)
        response["Retry-After"] = str(retry_after)
        return response

    form = LoginForm(request, data=request.POST)
    if form.is_valid():
        auth.login(request, form.user)  # troca a chave da sessão
        return redirect(_safe_next(request) or _home_for(form.user))
    _register_login_failure(limits)
    context["form"] = form
    return render(request, "accounts/login.html", context)


@require_POST
def logout(request: HttpRequest) -> HttpResponse:
    auth.logout(request)
    return redirect("catalog:home")


# Senha --------------------------------------------------------------------------


def _requires_reset_enabled(view):
    """Com a recuperação desligada, mostra o contato (se houver) e não chama a view."""

    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not password_reset_enabled():
            context = {"contact_email": settings.PRIVACY_CONTACT_EMAIL}
            return render(request, "accounts/password_reset_unavailable.html", context)
        return view(request, *args, **kwargs)

    return wrapped


password_reset = _requires_reset_enabled(
    ratelimit.rate_limited(SCOPE_RESET, RESET_LIMIT, RESET_WINDOW_S)(
        auth_views.PasswordResetView.as_view(
            form_class=ResetRequestForm,
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            extra_email_context={"subject": texts.PASSWORD_RESET_SUBJECT},
            success_url=reverse_lazy("accounts:password_reset_done"),
        )
    )
)

password_reset_done = auth_views.PasswordResetDoneView.as_view(
    template_name="accounts/password_reset_done.html",
)

password_reset_confirm = _requires_reset_enabled(
    auth_views.PasswordResetConfirmView.as_view(
        form_class=NewPasswordForm,
        template_name="accounts/password_reset_confirm.html",
        success_url=reverse_lazy("accounts:password_reset_complete"),
    )
)

password_reset_complete = auth_views.PasswordResetCompleteView.as_view(
    template_name="accounts/password_reset_complete.html",
)


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def password_change(request: HttpRequest) -> HttpResponse:
    data = request.POST if request.method == "POST" else None
    form = ChangePasswordForm(request.user, data)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth.update_session_auth_hash(request, user)  # continua logado; outras sessões saem
        messages.success(request, texts.PASSWORD_CHANGED)
        return redirect(_profile_url(user))
    context = {"form": form, "back_url": _profile_url(request.user)}
    return render(request, "accounts/password_change.html", context)


# Exclusão de conta ------------------------------------------------------------


@sensitive_post_parameters("password")
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request: HttpRequest) -> HttpResponse:
    """Exclui a conta com a senha (CA15).

    `user.delete()` apaga em cascata o vendedor, os anúncios, as variações, as
    fotos (os arquivos somem depois do commit, em `catalog/signals.py`), as
    denúncias e as métricas dos anúncios. Tudo numa transação: ou some tudo, ou nada.
    """
    user = request.user
    context = {"back_url": _profile_url(user)}
    if request.method != "POST":
        context["form"] = DeleteAccountForm(user)
        return render(request, "accounts/delete_account.html", context)

    key = ratelimit.user_key(request)
    if ratelimit.is_blocked(SCOPE_DELETE, key, DELETE_LIMIT, DELETE_WINDOW_S):
        context.update(form=DeleteAccountForm(user), limit_message=texts.DELETE_RATE_LIMITED)
        response = render(request, "accounts/delete_account.html", context, status=429)
        response["Retry-After"] = str(DELETE_WINDOW_S)
        return response

    form = DeleteAccountForm(user, request.POST)
    if not form.is_valid():
        ratelimit.register(SCOPE_DELETE, key, DELETE_WINDOW_S)
        context["form"] = form
        return render(request, "accounts/delete_account.html", context)

    with transaction.atomic():
        user.delete()
    auth.logout(request)
    messages.success(request, texts.ACCOUNT_DELETED)
    return redirect("catalog:home")
