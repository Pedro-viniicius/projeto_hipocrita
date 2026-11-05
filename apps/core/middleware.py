"""Middlewares do núcleo: healthz antecipado, cabeçalhos de segurança (CSP etc.)
e limite do tamanho do corpo da requisição."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.html import escape

from apps.core.views import healthz
from texts import photos as photo_texts

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    """Põe `Content-Security-Policy` (de `settings.CONTENT_SECURITY_POLICY`) e
    `Permissions-Policy` em toda resposta que ainda não os tenha.

    O CSP não libera script nem estilo inline: nada de `<script>` sem `src`,
    `style=""` ou `on*=` nos templates.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.policy = settings.CONTENT_SECURITY_POLICY

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", self.policy)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response


class HealthzMiddleware:
    """Responde `/healthz` antes da validação de `ALLOWED_HOSTS` e do redirecionamento
    HTTPS, para que o healthcheck interno (http://127.0.0.1:8000/healthz) funcione
    em produção com qualquer domínio configurado.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path_info == "/healthz" and request.method in {"GET", "HEAD"}:
            return healthz(request)
        return self.get_response(request)


REQUEST_TOO_LARGE_HTML = """<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Pão de Cada Dia</title></head>
<body><main id="conteudo" tabindex="-1"><h1>{title}</h1><p>{text}</p>
<p><a href="/">{back}</a></p></main></body>
</html>
"""


def _content_length(request: HttpRequest) -> int:
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return 0  # o Django também trata Content-Length inválido como corpo vazio


class RequestSizeLimitMiddleware:
    """Responde 413 quando o `Content-Length` passa de `settings.MAX_REQUEST_BODY_BYTES`.

    `DATA_UPLOAD_MAX_MEMORY_SIZE` não conta os arquivos de um multipart, então
    sem isto um envio de fotos não teria teto. A checagem vem antes de qualquer
    leitura do corpo (sessão, CSRF, `request.POST`). Sem `Content-Length`, o
    Django lê o corpo como vazio, então o cabeçalho é a medida que vale.
    A página é simples e autocontida: não depende de sessão, banco nem template.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.limit = settings.MAX_REQUEST_BODY_BYTES

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if _content_length(request) > self.limit:
            return self.too_large()
        return self.get_response(request)

    @staticmethod
    def too_large() -> HttpResponse:
        html = REQUEST_TOO_LARGE_HTML.format(
            title=escape(photo_texts.REQUEST_TOO_LARGE_TITLE),
            text=escape(photo_texts.REQUEST_TOO_LARGE_TEXT.format(mb=settings.MAX_UPLOAD_MB)),
            back=escape(photo_texts.REQUEST_TOO_LARGE_BACK),
        )
        response = HttpResponse(html, status=413, content_type="text/html; charset=utf-8")
        # O cliente ainda pode estar enviando o corpo: fechar evita reaproveitar a conexão.
        response["Connection"] = "close"
        return response
