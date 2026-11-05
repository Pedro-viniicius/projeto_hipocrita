"""Views do núcleo: saúde, limpeza agendada, robots, mídia, privacidade, estilos e erros."""

import hmac
import math
from pathlib import PurePosixPath
from types import SimpleNamespace

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.db import connection
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.template import loader
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_safe
from django.views.static import serve

from apps.core import retention
from texts import common as texts

MEDIA_EXTENSIONS = {".webp"}


@never_cache
@require_safe
def healthz(request: HttpRequest) -> HttpResponse:
    """200 "ok" se o app responde e o banco aceita consulta; 503 se o banco falha."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return HttpResponse("db indisponível", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")


@never_cache
@require_GET
def cleanup_cron(request: HttpRequest) -> HttpResponse:
    """Roda o `cleanup_data` quando chamado pelo agendador (Vercel Cron, GitHub Actions).

    Sem `CRON_SECRET` configurado a rota não existe (404). Com ele, exige o
    cabeçalho `Authorization: Bearer <CRON_SECRET>`, comparado em tempo constante;
    qualquer outro valor dá 401. A resposta é sempre "ok", sem as contagens: quem
    chama não precisa saber o que foi apagado. A limpeza é idempotente, então uma
    chamada repetida não faz mal.

    Compara bytes: o servidor WSGI entrega o cabeçalho decodificado em latin-1
    (PEP 3333), então voltar para latin-1 recupera os bytes enviados, que o agendador
    manda em UTF-8. Assim um segredo fora do ASCII também funciona (o `check --deploy`
    avisa, core.W002). Texto que não cabe em latin-1 não veio de um servidor real: 401.
    """
    secret = settings.CRON_SECRET
    if not secret:
        raise Http404
    try:
        received = request.headers.get("Authorization", "").encode("latin-1")
    except UnicodeEncodeError:
        received = b""
    expected = f"Bearer {secret}".encode()
    if not hmac.compare_digest(received, expected):
        response = HttpResponse(
            "não autorizado", status=401, content_type="text/plain; charset=utf-8"
        )
        response["WWW-Authenticate"] = "Bearer"
        return response
    call_command("cleanup_data")
    return HttpResponse("ok", content_type="text/plain")


ROBOTS_TXT = """User-agent: *
Disallow: /oferta/*/whatsapp/
Disallow: /oferta/*/denunciar/
Disallow: /meus-anuncios/
Disallow: /perfil/
Disallow: /admin/
Disallow: /entrar/
Disallow: /cadastrar/
Disallow: /sair/
Disallow: /senha/
Disallow: /_estilos/
"""


@require_safe
def robots_txt(request: HttpRequest) -> HttpResponse:
    return HttpResponse(ROBOTS_TXT, content_type="text/plain; charset=utf-8")


@require_safe
def media(request: HttpRequest, path: str) -> HttpResponse:
    """Serve as fotos do storage local. Com S3 a rota não existe (404).

    Só entrega `.webp` (o formato que o app grava), com `nosniff` e um dia de
    cache. Sem `immutable` nem cache de um ano: os nomes são UUID e nunca são
    reaproveitados, mas a foto apagada (anúncio ou conta excluída) não deve
    continuar em caches por muito tempo.
    """
    if settings.STORAGE_BACKEND != "local":
        raise Http404
    parts = PurePosixPath(path)
    if parts.is_absolute() or ".." in parts.parts or "\\" in path:
        raise Http404
    if parts.suffix.lower() not in MEDIA_EXTENSIONS:
        raise Http404
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=86400"
    response["Content-Type"] = "image/webp"
    return response


@require_safe
def privacy(request: HttpRequest) -> HttpResponse:
    """Página de privacidade. Responsável e contato vêm do ambiente; prazos, do código."""
    context = {
        "controller_name": settings.PRIVACY_CONTROLLER_NAME,
        "contact_email": settings.PRIVACY_CONTACT_EMAIL,
        "rate_limit_hours": retention.RATE_LIMIT_HOURS,
        # Em dias, arredondado para cima: a página nunca mostra prazo menor que o real.
        "rate_limit_max_days_if_scheduler_fails": math.ceil(
            retention.RATE_LIMIT_MAX_HOURS_IF_SCHEDULER_FAILS / 24
        ),
        "search_miss_days": retention.SEARCH_MISS_DAYS,
        "report_details_days": retention.REPORT_DETAILS_DAYS,
        "session_days": settings.SESSION_COOKIE_AGE // 86400,
    }
    return render(request, "core/privacy.html", context)


class StyleguideForm(forms.Form):
    """Formulário de exemplo para o designer ver campo, dica e erro renderizados."""

    title = forms.CharField(label="Título", max_length=80, help_text="Até 80 caracteres.")
    category = forms.ChoiceField(
        label="Categoria", choices=[("", "Escolha"), ("comidas", "Comidas e doces")]
    )
    kind = forms.ChoiceField(
        label="Tipo de oferta",
        widget=forms.RadioSelect,
        choices=[("recurring", "Recorrente"), ("daily", "Do dia"), ("one_off", "Venda pontual")],
    )
    description = forms.CharField(label="Descrição", widget=forms.Textarea, required=False)
    authorize = forms.BooleanField(label="Autorizo exibir meu WhatsApp", required=False)
    photos = forms.FileField(label="Fotos", required=False)


def _example_state(key: str, label: str, icon: str) -> SimpleNamespace:
    return SimpleNamespace(key=key, label=label, icon=icon)


STYLEGUIDE_STATES = [
    _example_state("available_today", "Disponível hoje", "circulo-check"),
    _example_state("on_order", "Sob encomenda", "relogio"),
    _example_state("sold_out", "Esgotado", "circulo-menos"),
    _example_state("sold", "Vendido", "etiqueta-check"),
    _example_state("paused", "Pausado", "pausa"),
    _example_state("needs_confirmation", "Precisa de confirmação", "alerta-circulo"),
    _example_state("pending_approval", "Aguardando aprovação", "ampulheta"),
]


def _example_card(pk: int, **fields) -> SimpleNamespace:
    """Cartão de exemplo com exatamente os campos do contrato `OfferCardVM`."""
    data = {
        "anchor_id": f"oferta-{pk}",
        "url": f"/oferta/{pk}/",
        "title": "Brigadeiro gourmet (exemplo)",
        "photo_url": None,
        "photo_w": 480,
        "photo_h": 480,
        "price_label": "R$ 3,50",
        "price_from": False,
        "price_struck": False,
        "state": STYLEGUIDE_STATES[0],
        "seller_name": "Doces da Ana (exemplo)",
        "fulfillment": "Retirada no bloco 3 às 10h",
        "eager": pk <= 2,
    }
    data.update(fields)
    return SimpleNamespace(**data)


def styleguide_cards() -> list[SimpleNamespace]:
    long_title = "Marmita fitness de frango com batata-doce e legumes no vapor (exemplo)"
    return [
        _example_card(1),
        _example_card(
            2,
            title="Bolo de pote (exemplo)",
            price_label="R$ 8,00",
            price_from=True,
            state=STYLEGUIDE_STATES[1],
        ),
        _example_card(3, title=long_title, state=STYLEGUIDE_STATES[2]),
        _example_card(
            4,
            title="Calculadora HP 50g (exemplo)",
            price_label="R$ 250,00",
            price_struck=True,
            state=STYLEGUIDE_STATES[3],
            seller_name="Bruno C. (exemplo)",
            fulfillment="Entrega no campus",
        ),
        _example_card(5, title="Aula de Cálculo I (exemplo)", state=None),
    ]


@require_safe
def styleguide(request: HttpRequest) -> HttpResponse:
    """Guia de estilos com dados de exemplo. Só existe com DEBUG=true."""
    if not settings.DEBUG:
        raise Http404
    form = StyleguideForm(data={"title": "", "category": "", "description": "Texto"})
    form.is_valid()
    messages.success(request, "Anúncio salvo. (exemplo)")
    messages.error(request, "Não foi possível salvar. Confira os campos marcados. (exemplo)")
    context = {
        "cards": styleguide_cards(),
        "states": STYLEGUIDE_STATES,
        "form": form,
    }
    return render(request, "core/styleguide.html", context)


# Páginas de erro -------------------------------------------------------------


def bad_request(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=400)


def permission_denied(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/403.html", {"message": texts.FORBIDDEN_TEXT}, status=403)


def page_not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    """500 sem contexto da requisição: funciona mesmo se o banco ou a sessão falharem."""
    html = loader.get_template("errors/500.html").render()
    return HttpResponse(html, status=500)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    """Falha de CSRF: 403 com a página do projeto (sem o motivo técnico)."""
    return render(request, "errors/403.html", {"message": texts.CSRF_FAILED_TEXT}, status=403)
