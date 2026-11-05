"""Teto do corpo da requisição (413) e log de host inválido em produção."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

from apps.core.testing import assert_lang_pt_br, assert_main_landmark
from texts import photos as texts

BASE_DIR = Path(settings.BASE_DIR)
MB = 1024 * 1024


def test_limit_is_three_photos_plus_slack():
    assert settings.MAX_UPLOAD_MB == 5
    assert settings.MAX_REQUEST_BODY_BYTES == 16 * MB


@pytest.mark.django_db
def test_body_over_limit_gets_413_before_reading(client):
    limit = settings.MAX_REQUEST_BODY_BYTES
    response = client.generic(
        "POST", "/entrar/", b"x", content_type="multipart/form-data; boundary=x",
        CONTENT_LENGTH=str(limit + 1),
    )  # fmt: skip
    assert response.status_code == 413
    assert response["Connection"] == "close"
    assert "Content-Security-Policy" in response.headers
    assert_lang_pt_br(response)
    assert_main_landmark(response)
    assert texts.REQUEST_TOO_LARGE_TITLE in response.content.decode()
    assert "Set-Cookie" not in response.headers


@pytest.mark.django_db
def test_body_at_limit_passes(client):
    response = client.generic(
        "POST", "/entrar/", b"", CONTENT_LENGTH=str(settings.MAX_REQUEST_BODY_BYTES)
    )
    assert response.status_code != 413


@pytest.mark.django_db
def test_invalid_content_length_is_ignored(client):
    assert client.generic("GET", "/entrar/", CONTENT_LENGTH="abc").status_code == 200


def test_limit_follows_max_upload_setting():
    code = "import config.settings as s; print(s.MAX_REQUEST_BODY_BYTES)"
    result = _run(code, {"DEBUG": "true", "MAX_UPLOAD_MB": "2"})
    assert result.stdout.strip() == str(7 * MB)


# DisallowedHost ------------------------------------------------------------------


def _run(code: str, env: dict) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if k not in {"SECRET_KEY", "DEBUG"}}
    clean.update(env)
    return subprocess.run(  # noqa: S603  (comando fixo, sem entrada externa)
        [sys.executable, "-c", code],
        cwd=BASE_DIR,
        env=clean,
        capture_output=True,
        text=True,
        check=True,
    )


def _app_handlers(logger: logging.Logger) -> list[logging.Handler]:
    """Handlers da configuração do app (o pytest 9 pendura os dele em todo logger)."""
    return [h for h in logger.handlers if not type(h).__module__.startswith("_pytest")]


@pytest.mark.django_db
def test_disallowed_host_is_silenced_in_production(client):
    assert settings.DEBUG is False
    assert settings.LOGGING["loggers"]["django.security.DisallowedHost"] == {
        "handlers": ["null"],
        "propagate": False,
    }
    logger = logging.getLogger("django.security.DisallowedHost")
    assert logger.propagate is False
    handlers = _app_handlers(logger)
    assert handlers and all(type(h) is logging.NullHandler for h in handlers)
    # O host inválido continua recusado (400); só o log some.
    assert client.get("/entrar/", HTTP_HOST="malicioso.example").status_code == 400


def test_disallowed_host_still_logged_with_debug():
    code = (
        "import config.settings as s; "
        "print('django.security.DisallowedHost' in s.LOGGING['loggers'])"
    )
    assert _run(code, {"DEBUG": "true"}).stdout.strip() == "False"
    prod = {"DEBUG": "false", "SECRET_KEY": "x" * 50}
    assert _run(code, prod).stdout.strip() == "True"
