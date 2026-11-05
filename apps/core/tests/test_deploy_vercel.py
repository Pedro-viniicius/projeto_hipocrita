"""Publicação na Vercel: pyproject, vercel.json, .vercelignore, build e cron (CA1, CA5)."""

import json
import os
import re
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import resolve

BASE_DIR = Path(settings.BASE_DIR)
VERCEL_JSON = BASE_DIR / "vercel.json"
WORKFLOW = BASE_DIR / ".github/workflows/limpeza.yml"
BUILD_SCRIPT = BASE_DIR / "scripts/vercel_build.sh"


def _pyproject() -> dict:
    return tomllib.loads((BASE_DIR / "pyproject.toml").read_text())


def _vercel() -> dict:
    return json.loads(VERCEL_JSON.read_text())


# Dependências e entrada WSGI ----------------------------------------------------


def test_pyproject_dependencies_match_requirements_txt():
    # Com pyproject e requirements e sem lockfile, a Vercel instala pelo pyproject;
    # o Dockerfile instala pelo requirements.txt. Os dois precisam ser iguais.
    lines = (BASE_DIR / "requirements.txt").read_text().splitlines()
    pins = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    assert pins, "requirements.txt sem dependências?"
    assert _pyproject()["project"]["dependencies"] == pins


def test_python_version_is_314():
    assert _pyproject()["project"]["requires-python"] == ">=3.14"


def test_entrypoint_is_the_wsgi_application():
    module, _, name = settings.WSGI_APPLICATION.rpartition(".")
    assert _pyproject()["tool"]["vercel"]["entrypoint"] == f"{module}:{name}"


def test_build_script_is_wired_and_valid_shell():
    assert _pyproject()["tool"]["vercel"]["scripts"]["build"] == "sh scripts/vercel_build.sh"
    assert BUILD_SCRIPT.stat().st_mode & stat.S_IXUSR
    result = subprocess.run(  # noqa: S603  (comando fixo)
        ["sh", "-n", str(BUILD_SCRIPT)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# Script de build: migrate só em produção, pela conexão direta ---------------------


@pytest.fixture
def fake_python(tmp_path):
    """Um `python` falso no PATH que registra o POSTGRES_HOST e os argumentos."""
    log = tmp_path / "chamadas.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "python"
    fake.write_text(f'#!/bin/sh\necho "${{POSTGRES_HOST:-}}|$*" >> "{log}"\n')
    fake.chmod(0o755)
    return bin_dir, log


def _run_build(bin_dir: Path, env: dict) -> subprocess.CompletedProcess:
    base = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(  # noqa: S603  (comando fixo, ambiente controlado)
        ["sh", str(BUILD_SCRIPT)],  # noqa: S607
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def _calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_build_in_production_migrates_through_direct_connection(fake_python):
    bin_dir, log = fake_python
    env = {
        "VERCEL_ENV": "production",
        "POSTGRES_HOST": "ep-x-pooler.sa-east-1.aws.neon.invalid",
        "PGHOST_UNPOOLED": "ep-x.sa-east-1.aws.neon.invalid",
    }
    result = _run_build(bin_dir, env)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == [
        "ep-x.sa-east-1.aws.neon.invalid|manage.py migrate --noinput",
        "ep-x-pooler.sa-east-1.aws.neon.invalid|manage.py check --deploy",
    ]


def test_build_in_production_without_unpooled_host_uses_postgres_host(fake_python):
    bin_dir, log = fake_python
    result = _run_build(bin_dir, {"VERCEL_ENV": "production", "POSTGRES_HOST": "db.invalid"})
    assert result.returncode == 0, result.stderr
    assert _calls(log)[0] == "db.invalid|manage.py migrate --noinput"


def test_build_in_production_without_database_host_fails(fake_python):
    # Sem host o migrate iria para o SQLite do build e o banco real ficaria sem migração.
    bin_dir, log = fake_python
    result = _run_build(bin_dir, {"VERCEL_ENV": "production", "POSTGRES_HOST": ""})
    assert result.returncode != 0
    assert "POSTGRES_HOST" in result.stderr
    assert _calls(log) == []


@pytest.mark.parametrize("vercel_env", [None, "preview", "development"])
def test_build_outside_production_never_migrates(fake_python, vercel_env):
    bin_dir, log = fake_python
    env = {"POSTGRES_HOST": "db.invalid"}
    if vercel_env is not None:
        env["VERCEL_ENV"] = vercel_env
    result = _run_build(bin_dir, env)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == ["db.invalid|manage.py check --deploy"]


# vercel.json -----------------------------------------------------------------------


def test_vercel_json_function_matches_entrypoint():
    config = _vercel()
    module = _pyproject()["tool"]["vercel"]["entrypoint"].split(":")[0]
    function_file = module.replace(".", "/") + ".py"
    assert list(config["functions"]) == [function_file]
    assert (BASE_DIR / function_file).is_file()
    assert config["functions"][function_file]["maxDuration"] == 60
    excluded = config["functions"][function_file]["excludeFiles"]
    assert "apps/**/tests/**" in excluded


def test_vercel_json_region_is_sao_paulo():
    assert _vercel()["regions"] == ["gru1"]


def test_every_cron_path_is_the_cleanup_route():
    crons = _vercel()["crons"]
    assert crons, "vercel.json sem cron de limpeza"
    for cron in crons:
        assert resolve(cron["path"]).view_name == "core:cleanup_cron"


def test_crons_run_at_most_daily_for_the_hobby_plan():
    # No Hobby, expressão que roda mais de 1 vez por dia derruba o deploy.
    for cron in _vercel()["crons"]:
        minute, hour, *_ = cron["schedule"].split()
        assert minute.isdigit(), cron["schedule"]
        assert hour.isdigit(), cron["schedule"]


@pytest.mark.parametrize(("vercel_env", "skips"), [("production", False), ("preview", True)])
def test_ignore_command_builds_only_production(vercel_env, skips):
    # Exit 0 no Ignored Build Step = pular o build. Previews não tocam no banco real.
    command = _vercel()["ignoreCommand"]
    result = subprocess.run(  # noqa: S603  (comando do próprio repositório)
        ["sh", "-c", command],  # noqa: S607
        env={"PATH": os.environ["PATH"], "VERCEL_ENV": vercel_env},
        check=False,
    )
    assert (result.returncode == 0) is skips


# .vercelignore ---------------------------------------------------------------------


def test_vercelignore_never_uploads_env_files():
    lines = {
        line.strip()
        for line in (BASE_DIR / ".vercelignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert {".env", ".env.*", "!.env.example"} <= lines
    assert {"db.sqlite3", "media/", ".claude/"} <= lines


# GitHub Actions: limpeza de 30 em 30 minutos (Hobby) --------------------------------


def test_workflow_calls_cleanup_route_every_30_minutes_without_permissions():
    # R1/S1: o GitHub atrasa e descarta execuções; de 30 em 30 minutos sobra folga.
    text = WORKFLOW.read_text()
    assert re.search(r'^\s+- cron: "7,37 \* \* \* \*"$', text, flags=re.MULTILINE)
    assert re.search(r"^  workflow_dispatch:$", text, flags=re.MULTILINE)
    assert re.search(r"^permissions: \{\}$", text, flags=re.MULTILINE)
    url = re.search(r'"\$\{SITE_URL%/\}(/[^"]+)"', text)
    assert url, "o workflow não chama a rota pela SITE_URL"
    assert resolve(url.group(1)).view_name == "core:cleanup_cron"


def test_workflow_keeps_secret_and_response_out_of_the_log():
    text = WORKFLOW.read_text()
    # O segredo entra só pelo bloco env (nunca interpolado direto no script).
    assert text.count("${{ secrets.CRON_SECRET }}") == 1
    assert re.search(r"^\s+CRON_SECRET: \$\{\{ secrets\.CRON_SECRET \}\}$", text, re.MULTILINE)
    run = text.split("run: |", 1)[1]
    assert "${{" not in run
    # O corpo vai para um arquivo temporário, apagado no fim, e nunca é impresso.
    assert '--output "$body_file"' in run
    assert "trap 'rm -f \"$body_file\"' EXIT" in run
    for leak in ("set -x", "--verbose", " -v ", "--trace", 'echo "$CRON_SECRET', "env\n"):
        assert leak not in run
