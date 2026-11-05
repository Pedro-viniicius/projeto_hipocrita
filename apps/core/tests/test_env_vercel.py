"""Configuração para serverless (Vercel): pooler do banco, S3/R2 e segredo do cron."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config import env as envlib

BASE_DIR = Path(settings.BASE_DIR)
POSTGRES = {"POSTGRES_HOST": "db", "POSTGRES_DB": "x", "POSTGRES_USER": "u"}


# Banco: cursores no servidor e pooler em modo transação (CA2) -----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, False), ("", False), ("false", False), ("true", True), ("1", True)],
)
def test_disable_server_side_cursors_follows_env(tmp_path, raw, expected):
    env = dict(POSTGRES)
    if raw is not None:
        env["DB_DISABLE_SERVER_SIDE_CURSORS"] = raw
    db = envlib.build_databases(env, tmp_path)["default"]
    assert db["DISABLE_SERVER_SIDE_CURSORS"] is expected
    # O reuso de conexão com teste de saúde continua valendo com o pooler.
    assert db["CONN_MAX_AGE"] == 60
    assert db["CONN_HEALTH_CHECKS"] is True


def test_disable_server_side_cursors_rejects_garbage(tmp_path):
    env = {**POSTGRES, "DB_DISABLE_SERVER_SIDE_CURSORS": "talvez"}
    with pytest.raises(ImproperlyConfigured):
        envlib.build_databases(env, tmp_path)


def test_sqlite_ignores_pooler_option(tmp_path):
    env = {"DB_DISABLE_SERVER_SIDE_CURSORS": "true"}
    db = envlib.build_databases(env, tmp_path)["default"]
    assert db["ENGINE"] == "django.db.backends.sqlite3"
    assert "DISABLE_SERVER_SIDE_CURSORS" not in db


def _settings_in_subprocess(env: dict, expression: str) -> str:
    """Importa `config.settings` com outro ambiente e devolve `repr(expression)`."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("POSTGRES_", "DB_"))}
    clean.pop("CRON_SECRET", None)
    clean.update({"DEBUG": "false", "SECRET_KEY": "x" * 50, **env})
    result = subprocess.run(  # noqa: S603  (comando fixo, sem entrada externa)
        [sys.executable, "-c", f"import config.settings as s; print(repr({expression}))"],
        cwd=BASE_DIR,
        env=clean,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_pooler_option_reaches_django_databases():
    env = {**POSTGRES, "DB_DISABLE_SERVER_SIDE_CURSORS": "true"}
    out = _settings_in_subprocess(env, "s.DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS']")
    assert out == "True"


# Fotos no R2: credencial estática, sem o AWS_SESSION_TOKEN da plataforma (CA3) -


R2_ENV = {
    "STORAGE_BACKEND": "s3",
    "AWS_STORAGE_BUCKET_NAME": "fotos",
    "AWS_S3_REGION_NAME": "auto",
    "AWS_S3_ENDPOINT_URL": "https://conta.r2.cloudflarestorage.invalid",
}


def test_s3_options_pin_security_token_to_none(tmp_path):
    options = envlib.build_storages(R2_ENV, tmp_path)["default"]["OPTIONS"]
    assert "security_token" in options
    assert options["security_token"] is None


def test_s3_storage_ignores_session_token_from_environment(tmp_path, monkeypatch):
    from storages.backends.s3 import S3Storage

    monkeypatch.setenv("AWS_SESSION_TOKEN", "token-da-plataforma")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "token-da-plataforma")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "chave-r2")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "segredo-r2")
    options = envlib.build_storages(R2_ENV, tmp_path)["default"]["OPTIONS"]

    storage = S3Storage(**options)  # só monta o objeto: nenhuma chamada de rede

    assert storage.security_token is None
    # A chave do bucket continua vindo do ambiente (não passa pelo settings).
    assert storage.access_key == "chave-r2"
    # Prova de que o teste exercita algo: sem a opção, o token do ambiente entraria.
    assert S3Storage(bucket_name="fotos").security_token == "token-da-plataforma"


# Segredo do cron (CA5) --------------------------------------------------------


def test_cron_secret_defaults_to_empty():
    assert _settings_in_subprocess({}, "s.CRON_SECRET") == "''"


def test_cron_secret_is_read_and_stripped():
    out = _settings_in_subprocess({"CRON_SECRET": "  abc123  "}, "s.CRON_SECRET")
    assert out == "'abc123'"
