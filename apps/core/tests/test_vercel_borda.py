"""Publicação na Vercel, casos de borda: rota de limpeza, build, workflow, limites e Docker (QA).

Complementa test_cron.py, test_deploy_vercel.py e test_env_vercel.py sem repetir o que já provam.
"""

import logging
import os
import re
import subprocess
import sys
import textwrap
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.core.models import RateLimitCounter
from config import env as envlib

BASE_DIR = Path(settings.BASE_DIR)
URL = "/_tarefas/limpeza/"
SECRET = "segredo-qa-0123456789abcdefghijklmnopqrstuv"
AUTH = {"authorization": f"Bearer {SECRET}"}
MIB = 1024 * 1024


def _subprocess_settings(env: dict, expression: str) -> str:
    """Importa `config.settings` num processo novo, com o ambiente dado, e devolve `repr`."""
    clean = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("POSTGRES_", "DB_")) and k not in {"CRON_SECRET", "MAX_UPLOAD_MB"}
    }
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


@pytest.fixture
def cron_secret(settings):
    settings.CRON_SECRET = SECRET
    return SECRET


@pytest.fixture
def expired_counter(db):
    return RateLimitCounter.objects.create(
        scope="login_ip",
        key_hash="c" * 64,
        window_start=timezone.now() - timedelta(hours=25),
        count=1,
    )


# Rota de limpeza: segredo em branco ou só espaços -----------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\t \n"])
def test_blank_cron_secret_in_environment_keeps_route_off(raw):
    # Um segredo de espaços não pode virar "Bearer    " aceito como senha.
    assert _subprocess_settings({"CRON_SECRET": raw}, "s.CRON_SECRET") == "''"


@pytest.mark.django_db
def test_route_is_off_by_default_even_for_a_logged_in_admin(staff_client, expired_counter):
    # Sem CRON_SECRET (padrão do Docker) a rota não existe, nem para o administrador.
    assert settings.CRON_SECRET == ""
    assert staff_client.get(URL).status_code == 404
    assert staff_client.get(URL, headers=AUTH).status_code == 404
    assert RateLimitCounter.objects.filter(key_hash="c" * 64).exists()


# Rota de limpeza: credencial e meios alternativos ------------------------------------


@pytest.mark.django_db
def test_admin_session_without_the_secret_does_not_run_cleanup(
    staff_client, cron_secret, expired_counter
):
    # Sessão de administrador não substitui o segredo.
    response = staff_client.get(URL)
    assert response.status_code == 401
    assert RateLimitCounter.objects.filter(key_hash="c" * 64).exists()


@pytest.mark.django_db
def test_admin_session_with_the_secret_still_works(staff_client, cron_secret, expired_counter):
    assert staff_client.get(URL, headers=AUTH).status_code == 200
    assert not RateLimitCounter.objects.filter(key_hash="c" * 64).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "headers"),
    [
        (f"{URL}?secret={SECRET}", {}),
        (f"{URL}?CRON_SECRET={SECRET}", {}),
        (f"{URL}?authorization=Bearer+{SECRET}", {}),
        (URL, {"x-cron-secret": SECRET}),
        (URL, {"x-forwarded-authorization": f"Bearer {SECRET}"}),
        (URL, {"cookie": f"authorization=Bearer {SECRET}"}),
    ],
)
def test_secret_only_counts_in_the_authorization_header(
    client, cron_secret, expired_counter, path, headers
):
    response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert RateLimitCounter.objects.filter(key_hash="c" * 64).exists()


@pytest.mark.django_db
def test_query_string_is_ignored_when_the_header_is_right(client, cron_secret, expired_counter):
    response = client.get(f"{URL}?q=banana&x=1", headers=AUTH)
    assert response.status_code == 200
    assert response.content == b"ok"
    assert not RateLimitCounter.objects.filter(key_hash="c" * 64).exists()


@pytest.mark.django_db
def test_path_without_trailing_slash_redirects_and_does_not_clean(
    client, cron_secret, expired_counter
):
    # O vercel.json e o workflow usam a barra final; sem ela só há o redirecionamento
    # (o cabeçalho não basta para limpar numa rota que não é a oficial).
    response = client.get("/_tarefas/limpeza", headers=AUTH)
    assert response.status_code == 301
    assert response.headers["Location"] == URL
    assert RateLimitCounter.objects.filter(key_hash="c" * 64).exists()


@pytest.mark.django_db
def test_unauthorized_calls_do_not_create_rate_limit_rows(client, cron_secret):
    # Quem erra o segredo não enche a tabela de contadores nem leva 429 (rota fora do limitador).
    for n in range(12):
        assert client.get(URL, headers={"authorization": f"Bearer errado-{n}"}).status_code == 401
    assert RateLimitCounter.objects.count() == 0
    assert client.get(URL, headers=AUTH).status_code == 200


@pytest.mark.django_db
def test_non_ascii_secret_authenticates_over_real_wsgi(client, settings):
    # Q1: a view compara os bytes recebidos (latin-1, PEP 3333) com o segredo em UTF-8.
    settings.CRON_SECRET = "sëgredo-çã"
    # Como o gunicorn/WSGI entrega: bytes do cabeçalho lidos como latin-1.
    delivered = "Bearer sëgredo-çã".encode().decode("latin-1")
    assert client.get(URL, HTTP_AUTHORIZATION=delivered).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("auth", ["Bearer sëgredo-çã", "Bearer segredo-€", "Bearer 秘密"])
def test_header_not_as_a_wsgi_server_delivers_gets_401_not_500(client, settings, auth):
    # O mesmo segredo sem passar por latin-1 (ou com caractere que nem cabe nele) não
    # autentica e não estoura.
    settings.CRON_SECRET = "sëgredo-çã"
    response = client.get(URL, HTTP_AUTHORIZATION=auth)
    assert response.status_code == 401


# Rota de limpeza: efeito, erro e sigilo ----------------------------------------------


@pytest.mark.django_db
def test_cleanup_also_removes_expired_sessions(client, cron_secret):
    Session.objects.create(
        session_key="vencida" + "0" * 25,
        session_data="x",
        expire_date=timezone.now() - timedelta(1),
    )
    Session.objects.create(
        session_key="valida" + "0" * 26, session_data="x", expire_date=timezone.now() + timedelta(1)
    )
    assert client.get(URL, headers=AUTH).status_code == 200
    assert list(Session.objects.values_list("session_key", flat=True)) == ["valida" + "0" * 26]


@pytest.mark.django_db
def test_failed_cleanup_is_not_reported_as_ok(cron_secret, expired_counter):
    # O cron precisa ver o erro (5xx) e tentar de novo; nunca um "ok" falso.
    from django.test import Client

    quiet = Client(raise_request_exception=False)
    with mock.patch("apps.core.views.call_command", side_effect=RuntimeError("banco caiu")):
        response = quiet.get(URL, headers=AUTH)
    assert response.status_code == 500
    assert response.content != b"ok"
    assert SECRET.encode() not in response.content
    assert b"banco caiu" not in response.content


@pytest.mark.django_db
def test_secret_never_reaches_the_log(client, cron_secret, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        client.get(URL, headers={"authorization": "Bearer " + SECRET + "x"})
        client.get(URL, headers=AUTH)
    out = capsys.readouterr()
    assert SECRET not in caplog.text
    assert SECRET not in out.out + out.err


@pytest.mark.django_db
def test_wrong_secret_is_not_echoed_in_the_response(client, cron_secret):
    guess = "tentativa-" + "z" * 20
    response = client.get(URL, headers={"authorization": f"Bearer {guess}"})
    assert guess.encode() not in response.content
    assert guess not in str(response.headers)


# Docker: com as variáveis novas ausentes, tudo como antes ---------------------------


def test_postgres_settings_without_new_variables_match_the_old_ones(tmp_path):
    env = {
        "POSTGRES_HOST": "db",
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
    }
    assert envlib.build_databases(env, tmp_path)["default"] == {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "db",
        "PORT": "5432",
        "NAME": "x",
        "USER": "u",
        "PASSWORD": "p",
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        # Igual ao padrão do Django: cursores no servidor continuam ligados.
        "DISABLE_SERVER_SIDE_CURSORS": False,
    }


def test_local_storage_options_are_untouched(tmp_path):
    storages = envlib.build_storages({}, tmp_path)
    assert "security_token" not in str(storages["default"])
    assert storages["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"


def test_s3_options_only_add_security_token(tmp_path):
    env = {"STORAGE_BACKEND": "s3", "AWS_STORAGE_BUCKET_NAME": "b"}
    options = envlib.build_storages(env, tmp_path)["default"]["OPTIONS"]
    without = {k: v for k, v in options.items() if k != "security_token"}
    assert options["security_token"] is None
    assert without["bucket_name"] == "b"
    # Nada de chave nem segredo na configuração do Django (o boto3 lê do ambiente).
    assert not {"access_key", "secret_key", "session_token"} & set(options)


def test_example_env_file_with_blank_new_variables_loads_like_docker():
    # O compose injeta `CRON_SECRET=` e `DB_DISABLE_SERVER_SIDE_CURSORS=false` do .env.example.
    out = _subprocess_settings(
        {"CRON_SECRET": "", "DB_DISABLE_SERVER_SIDE_CURSORS": "false", "MAX_UPLOAD_MB": "5"},
        "(s.CRON_SECRET, s.MAX_UPLOAD_MB, s.MAX_REQUEST_BODY_BYTES)",
    )
    assert out == f"('', 5, {16 * MIB})"


def test_example_env_has_no_active_pg_variables():
    # `PGSSLMODE=` vazio quebraria a libpq no compose: só podem estar comentadas.
    example = (BASE_DIR / ".env.example").read_text()
    active = set(re.findall(r"^([A-Z0-9_]+)=", example, flags=re.MULTILINE))
    assert not {"PGSSLMODE", "PGCHANNELBINDING", "PGHOST_UNPOOLED"} & active
    assert "CRON_SECRET" in active


def test_dockerfile_still_installs_from_requirements_txt():
    dockerfile = (BASE_DIR / "Dockerfile").read_text()
    assert "requirements.txt" in dockerfile
    assert "vercel" not in dockerfile.lower()


# Limite de corpo da Vercel (CA4) -----------------------------------------------------


def test_vercel_body_cap_fits_under_4_5_mb():
    # A Vercel recusa corpo acima de 4,5 MB (413 dela, fora do app).
    cap = int(_subprocess_settings({"MAX_UPLOAD_MB": "1"}, "s.MAX_REQUEST_BODY_BYTES"))
    assert cap == 4 * MIB
    assert cap < 4_500_000


# Script de build ---------------------------------------------------------------------

BUILD = BASE_DIR / "scripts/vercel_build.sh"


@pytest.fixture
def fake_python(tmp_path):
    """`python` falso: registra host, diretório e argumentos; falha se `FAKE_FAIL` aparece."""
    log = tmp_path / "chamadas.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "python"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "${{POSTGRES_HOST:-}}|$(pwd)|$*" >> "{log}"\n'
        'case "$*" in *"${FAKE_FAIL:-@@nunca@@}"*) exit 3 ;; esac\n'
    )
    fake.chmod(0o755)
    return bin_dir, log


def _build(bin_dir: Path, env: dict, cwd: Path | None = None):
    full = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", **env}
    return subprocess.run(  # noqa: S603  (comando fixo, ambiente controlado)
        ["sh", str(BUILD)],  # noqa: S607
        env=full,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_failed_migrate_fails_the_build_and_skips_the_rest(fake_python):
    bin_dir, log = fake_python
    env = {"VERCEL_ENV": "production", "POSTGRES_HOST": "db.invalid", "FAKE_FAIL": "migrate"}
    result = _build(bin_dir, env)
    assert result.returncode != 0
    calls = log.read_text().splitlines()
    assert len(calls) == 1 and "migrate" in calls[0]  # nem chegou ao check --deploy


def test_failing_check_deploy_fails_the_build(fake_python):
    bin_dir, _ = fake_python
    result = _build(bin_dir, {"POSTGRES_HOST": "db.invalid", "FAKE_FAIL": "check"})
    assert result.returncode != 0


def test_build_runs_from_the_project_root_whatever_the_cwd(fake_python, tmp_path):
    bin_dir, log = fake_python
    elsewhere = tmp_path / "outro"
    elsewhere.mkdir()
    result = _build(bin_dir, {"VERCEL_ENV": "production", "POSTGRES_HOST": "h"}, cwd=elsewhere)
    assert result.returncode == 0, result.stderr
    assert {line.split("|")[1] for line in log.read_text().splitlines()} == {str(BASE_DIR)}


def test_blank_unpooled_host_falls_back_to_postgres_host(fake_python):
    bin_dir, log = fake_python
    env = {"VERCEL_ENV": "production", "POSTGRES_HOST": "pooled.invalid", "PGHOST_UNPOOLED": ""}
    assert _build(bin_dir, env).returncode == 0
    assert log.read_text().splitlines()[0].startswith("pooled.invalid|")


def test_unpooled_host_alone_is_enough(fake_python):
    # Sem POSTGRES_HOST no ambiente, o host direto do Neon basta para migrar.
    bin_dir, log = fake_python
    result = _build(bin_dir, {"VERCEL_ENV": "production", "PGHOST_UNPOOLED": "direto.invalid"})
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines()[0].startswith("direto.invalid|")


@pytest.mark.parametrize("vercel_env", ["Production", "prod", "production ", ""])
def test_only_the_exact_word_production_migrates(fake_python, vercel_env):
    bin_dir, log = fake_python
    result = _build(bin_dir, {"VERCEL_ENV": vercel_env, "POSTGRES_HOST": "db.invalid"})
    assert result.returncode == 0, result.stderr
    assert all("migrate" not in line for line in log.read_text().splitlines())


def test_build_log_does_not_echo_credentials(fake_python):
    bin_dir, _ = fake_python
    env = {
        "VERCEL_ENV": "production",
        "POSTGRES_HOST": "db.invalid",
        "POSTGRES_PASSWORD": "senha-do-banco-qa",
        "SECRET_KEY": "chave-secreta-qa",
        "CRON_SECRET": SECRET,
    }
    result = _build(bin_dir, env)
    assert result.returncode == 0, result.stderr
    for secret in ("senha-do-banco-qa", "chave-secreta-qa", SECRET):
        assert secret not in result.stdout + result.stderr


# Workflow do GitHub Actions: o script do passo, com um curl falso ----------------------

WORKFLOW = BASE_DIR / ".github/workflows/limpeza.yml"


def _workflow_script() -> str:
    block = WORKFLOW.read_text().split("run: |\n", 1)[1]
    return textwrap.dedent(block)


# `curl` falso: grava argumentos e entrada padrão; escreve FAKE_BODY (padrão "ok") no
# arquivo de --output, imprime FAKE_STATUS (padrão 200) como o --write-out e sai com
# FAKE_EXIT (padrão 0; diferente de 0 simula falha de rede).
FAKE_CURL = """#!/bin/sh
printf "%s\\n" "$@" > "@ARGV@"
cat > "@STDIN@"
out=""
while [ $# -gt 0 ]; do
  [ "$1" = "--output" ] && out="$2"
  shift
done
[ -n "$out" ] && printf "%s" "${FAKE_BODY-ok}" > "$out"
printf "%s" "${FAKE_STATUS-200}"
exit "${FAKE_EXIT:-0}"
"""


@pytest.fixture
def fake_curl(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv, stdin = tmp_path / "argv.txt", tmp_path / "stdin.txt"
    fake = bin_dir / "curl"
    fake.write_text(FAKE_CURL.replace("@ARGV@", str(argv)).replace("@STDIN@", str(stdin)))
    fake.chmod(0o755)
    return bin_dir, argv, stdin


def _run_workflow(bin_dir: Path, env: dict):
    return subprocess.run(  # noqa: S603  (script do próprio repositório, curl falso)
        ["bash", "-e", "-c", _workflow_script()],  # noqa: S607
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_workflow_sends_secret_by_stdin_and_never_in_argv(fake_curl):
    bin_dir, argv, stdin = fake_curl
    result = _run_workflow(bin_dir, {"CRON_SECRET": SECRET, "SITE_URL": "https://site.exemplo/"})
    assert result.returncode == 0, result.stderr
    args = argv.read_text().splitlines()
    assert SECRET not in " ".join(args)  # `ps` não mostra o segredo
    assert stdin.read_text() == f"Authorization: Bearer {SECRET}\n"
    assert args[-1] == "https://site.exemplo/_tarefas/limpeza/"  # barra do SITE_URL tirada
    assert "--proto" in args and "--write-out" in args
    # Redirecionamento não é seguido (3xx falha o job, ver abaixo).
    assert not {"--location", "-L", "--location-trusted"} & set(args)
    assert SECRET not in result.stdout + result.stderr
    assert "Limpeza concluída." in result.stdout


@pytest.mark.parametrize(
    "env",
    [
        {"SITE_URL": "https://site.exemplo"},  # sem segredo
        {"CRON_SECRET": SECRET},  # sem URL
        {"CRON_SECRET": "", "SITE_URL": ""},
        {"CRON_SECRET": SECRET, "SITE_URL": "http://site.exemplo"},  # sem TLS
        {"CRON_SECRET": SECRET, "SITE_URL": "site.exemplo"},
    ],
)
def test_workflow_refuses_missing_secret_or_non_https_url(fake_curl, env):
    bin_dir, argv, _ = fake_curl
    result = _run_workflow(bin_dir, env)
    assert result.returncode != 0
    assert not argv.exists()  # o curl nem foi chamado: o segredo não vai por http
    assert SECRET not in result.stdout + result.stderr


BODY_MARKER = "corpo-da-resposta-qa"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        ("301", ""),  # sem barra final ou http → https: não é a limpeza
        ("302", ""),
        ("308", ""),
        ("401", f"não autorizado {BODY_MARKER}"),
        ("404", f"<html>{BODY_MARKER}</html>"),  # CRON_SECRET vazio na Vercel
        ("400", BODY_MARKER),  # host fora de ALLOWED_HOSTS
        ("500", BODY_MARKER),
        ("200", ""),  # 200 sem "ok" (ex.: página de login de alguma proteção)
        ("200", f"<html>{BODY_MARKER}</html>"),
        ("200", "OK"),
    ],
)
def test_workflow_fails_unless_200_with_ok(fake_curl, tmp_path, status, body):
    # R1/S1: só 200 com corpo "ok" é sucesso; 3xx não passa mais como verde.
    bin_dir, _, _ = fake_curl
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    env = {
        "CRON_SECRET": SECRET,
        "SITE_URL": "https://site.exemplo",
        "FAKE_STATUS": status,
        "FAKE_BODY": body,
        "TMPDIR": str(tmp),
    }
    result = _run_workflow(bin_dir, env)
    assert result.returncode != 0
    out = result.stdout + result.stderr
    assert f"HTTP {status}" in out
    assert "Limpeza concluída." not in out
    # Nem o segredo, nem o corpo, nem a URL completa vão para o log.
    for leak in (SECRET, BODY_MARKER, "/_tarefas/limpeza/"):
        assert leak not in out
    assert list(tmp.iterdir()) == []  # o arquivo do corpo foi apagado


def test_workflow_passes_with_200_ok_and_cleans_its_temp_file(fake_curl, tmp_path):
    bin_dir, _, _ = fake_curl
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    env = {"CRON_SECRET": SECRET, "SITE_URL": "https://site.exemplo", "TMPDIR": str(tmp)}
    result = _run_workflow(bin_dir, {**env, "FAKE_STATUS": "200", "FAKE_BODY": "ok"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Limpeza concluída."
    assert list(tmp.iterdir()) == []


def test_workflow_fails_when_the_site_does_not_answer(fake_curl, tmp_path):
    # curl sai com erro (DNS, conexão, TLS): o job falha com mensagem própria.
    bin_dir, _, _ = fake_curl
    env = {
        "CRON_SECRET": SECRET,
        "SITE_URL": "https://site.exemplo",
        "FAKE_STATUS": "000",
        "FAKE_EXIT": "6",
    }
    result = _run_workflow(bin_dir, env)
    assert result.returncode != 0
    out = result.stdout + result.stderr
    assert "não respondeu" in out
    assert SECRET not in out
