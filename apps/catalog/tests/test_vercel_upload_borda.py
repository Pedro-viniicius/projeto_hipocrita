"""Envio de fotos com `MAX_UPLOAD_MB=1` (Vercel), sem o JS de redução: o servidor responde
com a mensagem do app, nunca com 500 (CA4, QA)."""

import io

import pytest
import time_machine
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.models import Category, Offer
from apps.core.testing import parse_html
from texts import photos as photo_texts

pytestmark = pytest.mark.django_db

NEW_URL = "/meus-anuncios/novo/"
MB = 1024 * 1024
NOW = "2026-11-05 10:20:00-03:00"


@pytest.fixture(autouse=True)
def vercel_limits(settings):
    """O que a Vercel configura: 1 MB por foto e corpo de até 3 × 1 + 1 = 4 MiB.

    Os dois valores vêm de `config/settings.py` na carga; aqui repetimos a conta para o
    teste, antes do primeiro request (o middleware lê o teto ao montar a cadeia).
    """
    settings.MAX_UPLOAD_MB = 1
    settings.MAX_REQUEST_BODY_BYTES = (3 * 1 + 1) * MB


def jpeg_of(size: int) -> bytes:
    """JPEG válido de exatamente `size` bytes (lixo depois do EOI, que o Pillow ignora)."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 80, 40)).save(buf, format="JPEG")
    data = buf.getvalue()
    assert len(data) < size
    return data + b"\0" * (size - len(data))


def upload(data: bytes, n: int = 0) -> SimpleUploadedFile:
    return SimpleUploadedFile(f"foto{n}.jpg", data, content_type="image/jpeg")


def payload(**overrides) -> dict:
    data = {
        "kind": "recurring",
        "title": "Bolo de pote",
        "category": Category.objects.get(slug="comidas-e-doces").pk,
        "price": "8,50",
        "fulfillment": "Retirada no bloco 3",
    }
    data.update(overrides)
    return data


def stored() -> set[str]:
    try:
        _, files = default_storage.listdir("offers")
    except FileNotFoundError:
        return set()
    return set(files)


def photos_error(response) -> str:
    el = parse_html(response).find(id="id_photos_error")
    return el.text if el is not None else ""


@time_machine.travel(NOW, tick=False)
def test_three_photos_exactly_at_the_limit_are_accepted(seller_client):
    files = [upload(jpeg_of(1 * MB), n) for n in range(3)]
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 302
    assert Offer.objects.get().photos.count() == 3


@time_machine.travel(NOW, tick=False)
def test_photo_one_byte_over_the_limit_gets_the_app_message(seller_client):
    before = stored()
    response = seller_client.post(NEW_URL, {**payload(), "photos": [upload(jpeg_of(1 * MB + 1))]})
    assert response.status_code == 200
    assert photos_error(response) == photo_texts.PHOTO_TOO_LARGE.format(mb=1)
    assert "1 MB" in photos_error(response)
    assert not Offer.objects.exists()
    assert stored() == before
    # O formulário volta preenchido (o vendedor não perde o texto).
    assert parse_html(response).find("input", name="title").get("value") == "Bolo de pote"


@time_machine.travel(NOW, tick=False)
def test_three_phone_photos_under_the_body_cap_get_a_message_not_a_500(seller_client):
    # 3 × 1,3 MiB = 3,9 MiB: passa do teto de corpo? Não (4 MiB), então chega ao formulário.
    files = [upload(jpeg_of(int(1.3 * MB)), n) for n in range(3)]
    before = stored()
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 200
    assert photos_error(response) == photo_texts.PHOTO_TOO_LARGE.format(mb=1)
    assert not Offer.objects.exists()
    assert stored() == before


@time_machine.travel(NOW, tick=False)
def test_three_big_photos_over_the_body_cap_get_the_own_413_page(seller_client):
    # 3 × 1,5 MiB = 4,5 MiB > 4 MiB: o app responde 413 com a página dele (a da Vercel,
    # com 4,5 MB, só aparece acima disso).
    files = [upload(jpeg_of(int(1.5 * MB)), n) for n in range(3)]
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 413
    html = response.content.decode()
    assert photo_texts.REQUEST_TOO_LARGE_TITLE in html
    assert "até 1 MB cada" in html
    assert not Offer.objects.exists()


@time_machine.travel(NOW, tick=False)
def test_edit_with_oversized_photo_keeps_existing_photos(seller_client, make_offer):
    offer = make_offer(seller_client.seller)
    seller_client.post(
        f"/meus-anuncios/{offer.pk}/editar/", {**payload(), "photos": [upload(jpeg_of(MB))]}
    )
    assert offer.photos.count() == 1
    kept = set(offer.photos.values_list("pk", flat=True))
    response = seller_client.post(
        f"/meus-anuncios/{offer.pk}/editar/",
        {**payload(), "photos": [upload(jpeg_of(MB + 1))]},
    )
    assert response.status_code == 200
    assert photos_error(response) == photo_texts.PHOTO_TOO_LARGE.format(mb=1)
    assert set(offer.photos.values_list("pk", flat=True)) == kept


@time_machine.travel(NOW, tick=False)
def test_photo_reduced_like_the_browser_does_fits_and_is_saved(seller_client):
    # O que o fotos.js entrega: JPEG de lado maior 1280 px, qualidade 85, abaixo de 1 MB.
    img = Image.effect_noise((1280, 960), 40).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = buf.getvalue()
    assert data, "imagem de teste vazia"
    if len(data) > MB:  # imagem de ruído pesa mais que uma foto real: reduz só para o teste
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=40)
        data = buf.getvalue()
    assert len(data) <= MB
    files = [upload(data, n) for n in range(3)]
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 302
    photo = Offer.objects.get().photos.order_by("position").first()
    assert photo.page_width == 1280
