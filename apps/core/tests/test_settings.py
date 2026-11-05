"""Configuração: cookies, CSRF, CSP, storage, banco, logs e gunicorn (CA13, CA14, CA19)."""

import logging
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import Client, RequestFactory

from apps.core.logging import REDACTED, RedactDatabaseErrors
from apps.core.testing import assert_lang_pt_br, assert_main_landmark
from config import env as envlib

BASE_DIR = Path(settings.BASE_DIR)


# Cookies e CSRF (CA14) --------------------------------------------------------


def test_cookie_flags_in_settings():
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_HTTPONLY is True
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"
    # settings_test espelha produção (DEBUG=false): cookies só por HTTPS.
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True


@pytest.mark.parametrize(
    ("env", "debug", "secure"),
    [
        ({}, False, True),
        ({}, True, False),
        ({"COOKIE_SECURE": "false"}, False, False),
        ({"COOKIE_SECURE": "true"}, True, True),
        ({"COOKIE_SECURE": ""}, False, True),  # "COOKIE_SECURE=" no .env vale o padrão
    ],
)
def test_cookie_secure_follows_debug_unless_overridden(env, debug, secure):
    result = envlib.security_settings(env, debug=debug)
    assert result["SESSION_COOKIE_SECURE"] is secure
    assert result["CSRF_COOKIE_SECURE"] is secure
    assert result["SESSION_COOKIE_HTTPONLY"] is True
    assert result["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_proxy_ssl_header_only_when_enabled():
    assert envlib.security_settings({}, debug=False)["SECURE_PROXY_SSL_HEADER"] is None
    on = envlib.security_settings({"SECURE_PROXY_SSL_HEADER": "true"}, debug=False)
    assert on["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")


@pytest.mark.django_db
def test_session_cookie_is_httponly_samesite_secure():
    request = RequestFactory().get("/")
    middleware = SessionMiddleware(lambda req: HttpResponse("ok"))
    middleware.process_request(request)
    request.session["algo"] = 1
    response = middleware.process_response(request, HttpResponse("ok"))
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["secure"] is True


def _csrf_token_from(html: str) -> str:
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    assert match, "formulário sem csrfmiddlewaretoken"
    return match.group(1)


@pytest.mark.django_db
def test_csrf_cookie_flags_and_enforcement(settings):
    settings.DEBUG = True  # o guia de estilos tem um formulário POST
    client = Client(enforce_csrf_checks=True)
    page = client.get("/_estilos/")
    assert page.status_code == 200
    cookie = page.cookies[settings.CSRF_COOKIE_NAME]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["secure"] is True

    # Sem token: 403 com a página do projeto, sem detalhes técnicos.
    denied = client.post("/sair/")
    assert denied.status_code == 403
    assert b"CSRF" not in denied.content
    assert_lang_pt_br(denied)

    # Com token: passa pelo CSRF e o logout redireciona (302).
    token = _csrf_token_from(page.content.decode())
    allowed = client.post("/sair/", {"csrfmiddlewaretoken": token})
    assert allowed.status_code == 302


# CSP e cabeçalhos ------------------------------------------------------------


@pytest.mark.django_db
def test_security_headers_on_responses(client):
    response = client.get("/robots.txt")
    csp = response.headers["Content-Security-Policy"]
    directives = {d.split()[0]: d.split()[1:] for d in csp.split("; ")}
    assert directives["form-action"] == ["'self'", "https://wa.me", "https://api.whatsapp.com"]
    assert directives["script-src"] == ["'self'"]
    assert directives["style-src"] == ["'self'"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_csp_includes_s3_image_origin():
    env = {
        "STORAGE_BACKEND": "s3",
        "AWS_STORAGE_BUCKET_NAME": "fotos",
        "AWS_S3_ENDPOINT_URL": "https://fly.storage.tigris.dev",
    }
    csp = envlib.build_csp(envlib.storage_image_origins(env))
    assert "img-src 'self' data: https://fly.storage.tigris.dev" in csp
    assert envlib.storage_image_origins({"STORAGE_BACKEND": "local"}) == []
    custom = {"STORAGE_BACKEND": "s3", "AWS_S3_CUSTOM_DOMAIN": "cdn.exemplo.invalid"}
    assert envlib.storage_image_origins(custom) == ["https://cdn.exemplo.invalid"]


# Storage (CA13: local ou S3 por variável de ambiente) ------------------------


def test_storage_local_by_default(tmp_path):
    storages = envlib.build_storages({}, tmp_path)
    assert storages["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
    assert storages["default"]["OPTIONS"]["location"] == str(tmp_path)
    assert "whitenoise" in storages["staticfiles"]["BACKEND"]


def test_storage_s3_when_configured(tmp_path):
    env = {
        "STORAGE_BACKEND": "S3",
        "AWS_STORAGE_BUCKET_NAME": "fotos",
        "AWS_S3_REGION_NAME": "auto",
        "AWS_S3_ENDPOINT_URL": "https://exemplo.r2.invalid",
        "AWS_ACCESS_KEY_ID": "nao-deve-ir-para-settings",
    }
    storages = envlib.build_storages(env, tmp_path)
    options = storages["default"]["OPTIONS"]
    assert storages["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert options["bucket_name"] == "fotos"
    assert options["endpoint_url"] == "https://exemplo.r2.invalid"
    assert options["querystring_auth"] is True
    assert options["file_overwrite"] is False
    # Credenciais ficam com o boto3 (ambiente), nunca na configuração do Django.
    assert "nao-deve-ir-para-settings" not in repr(storages)


def test_storage_s3_requires_bucket_and_valid_backend(tmp_path):
    with pytest.raises(ImproperlyConfigured):
        envlib.build_storages({"STORAGE_BACKEND": "s3"}, tmp_path)
    with pytest.raises(ImproperlyConfigured):
        envlib.build_storages({"STORAGE_BACKEND": "ftp"}, tmp_path)


def test_s3_storage_class_imports():
    from storages.backends.s3 import S3Storage  # noqa: F401  (django-storages instalado)


# Banco, idioma, fuso e apps (CA19) ------------------------------------------


def test_database_sqlite_without_host(tmp_path):
    dbs = envlib.build_databases({}, tmp_path)
    assert dbs["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_database_postgres_with_host(tmp_path):
    env = {
        "POSTGRES_HOST": "db",
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
    }
    db = envlib.build_databases(env, tmp_path)["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert (db["HOST"], db["NAME"], db["USER"]) == ("db", "x", "u")


def test_language_timezone_and_apps():
    assert settings.LANGUAGE_CODE == "pt-br"
    assert settings.USE_TZ is True
    assert settings.COMMUNITY_TZ == "America/Sao_Paulo"
    assert settings.TIME_ZONE == settings.COMMUNITY_TZ
    assert "django.contrib.admin" not in settings.INSTALLED_APPS
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.MESSAGE_STORAGE.endswith("SessionStorage")


def test_blank_env_values_use_defaults():
    env = {"X": "  ", "TZ": ""}
    assert envlib.env_bool(env, "X", True) is True
    assert envlib.env_int(env, "X", 7) == 7
    assert envlib.env_str(env, "TZ", "America/Sao_Paulo") == "America/Sao_Paulo"
    assert envlib.env_list(env, "X", ["localhost"]) == ["localhost"]


ENV_READ = re.compile(
    r'env_(?:str|bool|int|list)\(\s*(?:ENV|env),\s*"([A-Z0-9_]+)"'
    r'|(?:ENV|env|os\.environ)\.get\(\s*"([A-Z0-9_]+)"'
)


def test_every_env_var_is_documented_in_env_example():
    sources = [*sorted((BASE_DIR / "config").glob("*.py")), BASE_DIR / "docker/gunicorn.conf.py"]
    used = set()
    for source in sources:
        if source.name == "settings_test.py":
            continue
        for match in ENV_READ.finditer(source.read_text()):
            used.add(match.group(1) or match.group(2))
    example = (BASE_DIR / ".env.example").read_text()
    documented = set(re.findall(r"^([A-Z0-9_]+)=", example, flags=re.MULTILINE))
    assert used, "nenhuma variável encontrada (regex quebrada?)"
    assert not used - documented, f"faltam no .env.example: {sorted(used - documented)}"


@pytest.mark.parametrize("raw", ["talvez", "2"])
def test_env_bool_rejects_garbage(raw):
    with pytest.raises(ImproperlyConfigured):
        envlib.env_bool({"X": raw}, "X")


def _import_settings(env: dict) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if k not in {"SECRET_KEY", "DEBUG"}}
    clean.update(env)
    return subprocess.run(  # noqa: S603  (comando fixo, sem entrada externa)
        [sys.executable, "-c", "import config.settings"],
        cwd=BASE_DIR,
        env=clean,
        capture_output=True,
        text=True,
        check=False,
    )


def test_secret_key_required_without_debug():
    result = _import_settings({"DEBUG": "false"})
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_secret_key_optional_with_debug():
    assert _import_settings({"DEBUG": "true"}).returncode == 0


def test_invalid_timezone_fails_fast():
    result = _import_settings({"DEBUG": "true", "COMMUNITY_TZ": "Lua/Base"})
    assert result.returncode != 0
    assert "COMMUNITY_TZ" in result.stderr


# Páginas de erro --------------------------------------------------------------


@pytest.mark.django_db
def test_404_uses_project_template(client):
    response = client.get("/nao-existe/")
    assert response.status_code == 404
    assert_lang_pt_br(response)
    assert_main_landmark(response)


def test_500_renders_without_request_context():
    from apps.core.views import server_error

    response = server_error(RequestFactory().get("/"))
    assert response.status_code == 500
    assert_lang_pt_br(response)


# Logs sem dado pessoal --------------------------------------------------------


def test_database_error_message_is_redacted_from_logs():
    # O valor vem de variável, como numa query real: o traceback mostra as linhas de
    # código (que não têm o dado), mas não a mensagem da exceção (que tem).
    email = "ana" + "@exemplo.test"
    try:
        try:
            raise ValueError(f"Key (email)=({email}) already exists")
        except ValueError as inner:
            raise IntegrityError(f"duplicate key: {email}") from inner
    except IntegrityError:
        record = logging.LogRecord(
            "django.request", logging.ERROR, __file__, 1, "Erro: %s", ("/x",), sys.exc_info()
        )
    assert RedactDatabaseErrors().filter(record) is True
    text = logging.Formatter().format(record)
    assert email not in text
    assert REDACTED in text
    assert "IntegrityError" in text


def test_db_logger_never_debug():
    assert settings.LOGGING["loggers"]["django.db.backends"]["level"] == "WARNING"


def test_gunicorn_access_log_has_no_ip_or_query():
    conf = runpy.run_path(str(BASE_DIR / "docker" / "gunicorn.conf.py"))
    fmt = conf["access_log_format"]
    for forbidden in ("%(h)s", "%(q)s", "%(r)s", "%(a)s", "%(f)s", "%({x-forwarded-for}i)s"):
        assert forbidden not in fmt
    assert "%(U)s" in fmt


# Link de redefinição de senha fora dos logs (S3) ------------------------------

RESET_PATH = "/senha/redefinir/MTIz/d4f1ab-0123456789abcdef0123456789abcdef/"


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


def test_reset_link_is_masked_by_django_log_filter():
    from apps.core.redaction import RedactPasswordResetLinks

    record = logging.LogRecord(
        "django.request", logging.WARNING, __file__, 1, "Not Found: %s", (RESET_PATH,), None
    )
    assert RedactPasswordResetLinks().filter(record) is True
    text = logging.Formatter().format(record)
    assert "MTIz" not in text
    assert "d4f1ab" not in text
    assert "/senha/redefinir/" in text
    assert "redact_reset_links" in settings.LOGGING["handlers"]["console"]["filters"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"GET {RESET_PATH} 200", "GET /senha/redefinir/*** 200"),
        ("/senha/redefinir/MTIz/set-password/", "/senha/redefinir/***"),
        ('"GET /senha/redefinir/a/b/?x=1"', '"GET /senha/redefinir/***"'),
        ("/senha/recuperar/", "/senha/recuperar/"),
        ("/oferta/7/", "/oferta/7/"),
    ],
)
def test_redact_reset_links(raw, expected):
    from apps.core.redaction import redact_reset_links

    assert redact_reset_links(raw) == expected


def test_gunicorn_logger_masks_reset_links_in_access_and_error_logs():
    from datetime import timedelta
    from types import SimpleNamespace

    from gunicorn.config import Config

    conf = runpy.run_path(str(BASE_DIR / "docker" / "gunicorn.conf.py"))
    cfg = Config()
    for name in ("accesslog", "errorlog", "access_log_format", "logger_class", "loglevel"):
        cfg.set(name, conf[name])
    logger = cfg.logger_class(cfg)
    handler = _ListHandler()
    logger.access_log.addHandler(handler)
    logger.error_log.addHandler(handler)
    try:
        environ = {
            "REQUEST_METHOD": "GET",
            "RAW_URI": RESET_PATH,
            "PATH_INFO": RESET_PATH,
            "QUERY_STRING": "",
            "SERVER_PROTOCOL": "HTTP/1.1",
        }
        resp = SimpleNamespace(status="302 Found", sent=0, headers=[])
        logger.access(resp, SimpleNamespace(headers=[]), environ, timedelta(milliseconds=3))
        logger.error("Error handling request %s", RESET_PATH)
        # Caminho comum continua aparecendo inteiro.
        environ.update(RAW_URI="/oferta/7/", PATH_INFO="/oferta/7/")
        logger.access(resp, SimpleNamespace(headers=[]), environ, timedelta(milliseconds=3))
    finally:
        logger.access_log.removeHandler(handler)
        logger.error_log.removeHandler(handler)
    assert len(handler.lines) == 3
    for line in handler.lines[:2]:
        assert "MTIz" not in line
        assert "d4f1ab" not in line
        assert "/senha/redefinir/***" in line
    assert '"GET /oferta/7/" 302' in handler.lines[2]
