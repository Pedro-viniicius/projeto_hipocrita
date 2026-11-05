"""Rotas do núcleo: healthz, robots, mídia local, privacidade e guia de estilos."""

from unittest import mock

import pytest

from apps.core.testing import assert_accessible_page, assert_no_set_cookie

pytestmark = pytest.mark.django_db


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"
    assert "no-cache" in response.headers["Cache-Control"]
    assert_no_set_cookie(response)


def test_healthz_head_and_any_host(client):
    # O healthcheck interno usa 127.0.0.1, que não está em ALLOWED_HOSTS.
    assert client.head("/healthz").status_code == 200
    assert client.get("/healthz", HTTP_HOST="127.0.0.1:8000").status_code == 200


def test_healthz_reports_database_failure(client):
    with mock.patch("apps.core.views.connection.cursor", side_effect=RuntimeError("fora")):
        response = client.get("/healthz")
    assert response.status_code == 503


def test_healthz_rejects_post(client):
    assert client.post("/healthz").status_code == 405


def test_robots_blocks_contact_and_private_areas(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    for rule in ("/oferta/*/whatsapp/", "/meus-anuncios/", "/admin/", "/perfil/"):
        assert f"Disallow: {rule}" in body


def test_media_serves_webp_with_nosniff(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "offers").mkdir()
    (tmp_path / "offers" / "abc-card.webp").write_bytes(b"RIFF....WEBP")
    response = client.get("/media/offers/abc-card.webp")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/webp"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    # Um dia de cache, sem "immutable": foto apagada não fica um ano em cache (S10).
    assert response.headers["Cache-Control"] == "public, max-age=86400"


def test_media_refuses_other_files_and_traversal(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "nota.html").write_text("<script>alert(1)</script>")
    assert client.get("/media/nota.html").status_code == 404
    assert client.get("/media/../settings.webp").status_code == 404
    assert client.get("/media/offers/nao-existe.webp").status_code == 404


def test_media_route_disabled_with_s3(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "x.webp").write_bytes(b"x")
    settings.STORAGE_BACKEND = "s3"
    assert client.get("/media/x.webp").status_code == 404


def test_privacy_page(client):
    response = client.get("/privacidade/")
    assert response.status_code == 200
    assert_accessible_page(response)
    assert_no_set_cookie(response)


def test_styleguide_only_in_debug(client, settings):
    assert client.get("/_estilos/").status_code == 404
    settings.DEBUG = True
    response = client.get("/_estilos/")
    assert response.status_code == 200
    assert_accessible_page(response)
    cards = response.context["cards"]
    expected = {
        "anchor_id", "url", "title", "photo_url", "photo_w", "photo_h", "price_label",
        "price_from", "price_struck", "state", "seller_name", "fulfillment", "eager",
    }  # fmt: skip
    assert all(set(vars(card)) == expected for card in cards)
