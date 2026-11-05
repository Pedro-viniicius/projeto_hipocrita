"""Fotos do anúncio: até 3, tipo real, tamanho, remoção e limite de envio (CA11, CA13, CA14)."""

import io
import re

import pytest
import time_machine
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory
from PIL import Image

from apps.catalog import services_seller
from apps.catalog.models import Category, Offer, OfferPhoto
from apps.catalog.photos import save_offer_photos
from apps.core import ratelimit
from apps.core.testing import make_image_bytes, parse_html
from texts import photos as photo_texts
from texts import seller as texts

pytestmark = pytest.mark.django_db

NEW_URL = "/meus-anuncios/novo/"
MB = 1024 * 1024
# Relógio parado: a janela do limite é fixa por hora e o teste não pode cruzar a virada.
NOW = "2026-11-05 10:20:00-03:00"


def upload(data: bytes, name: str = "foto.jpg", content_type: str = "image/jpeg"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def small_jpeg(color=(200, 80, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="JPEG")
    return buf.getvalue()


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


def edit_url(offer) -> str:
    return f"/meus-anuncios/{offer.pk}/editar/"


def stored() -> set[str]:
    try:
        _, files = default_storage.listdir("offers")
    except FileNotFoundError:
        return set()
    return {f"offers/{name}" for name in files}


def photos_error(response) -> str:
    el = parse_html(response).find(id="id_photos_error")
    return el.text if el is not None else ""


def add_photos(offer, count: int) -> list[OfferPhoto]:
    save_offer_photos(offer, [upload(small_jpeg()) for _ in range(count)], [])
    return list(offer.photos.order_by("position"))


def open_stored(name: str) -> Image.Image:
    with default_storage.open(name) as fh:
        img = Image.open(io.BytesIO(fh.read()))
        img.load()
    return img


# Envio (CA13) ------------------------------------------------------------------


def test_create_with_photos_stores_two_webp_sizes(seller_client, jpeg_bytes, png_bytes):
    before = stored()
    files = [upload(jpeg_bytes), upload(png_bytes, "outra.jpg")]  # PNG com nome .jpg
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 302
    offer = Offer.objects.get()
    photos = list(offer.photos.order_by("position"))
    assert [p.position for p in photos] == [0, 1]
    new_files = stored() - before
    assert len(new_files) == 4
    for photo in photos:
        assert re.fullmatch(r"offers/[0-9a-f]{32}-card\.webp", photo.card_image.name)
        assert re.fullmatch(r"offers/[0-9a-f]{32}-page\.webp", photo.page_image.name)
        card = open_stored(photo.card_image.name)
        page = open_stored(photo.page_image.name)
        assert card.format == page.format == "WEBP"
        assert card.size == (480, 480)
        assert page.size == (photo.page_width, photo.page_height)
        assert "exif" not in page.info
    # O nome enviado pelo usuário não chega ao storage.
    assert not any("foto" in name or "outra" in name for name in new_files)
    # A miniatura aparece no painel.
    doc = parse_html(seller_client.get("/meus-anuncios/"))
    img = doc.find("article", id=f"anuncio-{offer.pk}").find("img")
    assert img.get("src").endswith(photos[0].card_image.name)
    assert img.get("alt") == ""


def test_text_disguised_as_jpg_is_refused(seller_client, fake_jpg_text):
    before = stored()
    response = seller_client.post(NEW_URL, {**payload(), "photos": [upload(fake_jpg_text)]})
    assert response.status_code == 200
    assert photos_error(response) == photo_texts.PHOTO_INVALID
    assert not Offer.objects.exists()
    assert stored() == before
    # O resto do formulário volta preenchido, com o aviso de escolher as fotos de novo.
    doc = parse_html(response)
    assert doc.find("input", name="title").get("value") == "Bolo de pote"
    assert "escolha as fotos de novo" in doc.find(id="id_photos_helptext").text


def test_photo_over_size_limit_is_refused(seller_client, settings):
    big = small_jpeg() + b"\0" * (settings.MAX_UPLOAD_MB * MB)
    response = seller_client.post(NEW_URL, {**payload(), "photos": [upload(big)]})
    assert photos_error(response) == photo_texts.PHOTO_TOO_LARGE.format(mb=settings.MAX_UPLOAD_MB)
    assert not Offer.objects.exists()


def test_more_than_three_photos_at_once_is_refused(seller_client):
    files = [upload(small_jpeg()) for _ in range(4)]
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert photos_error(response) == texts.PHOTOS_TOO_MANY.format(max=3)
    assert not Offer.objects.exists()


def test_fourth_photo_on_edit_is_refused(seller_client, make_offer):
    offer = make_offer(seller_client.seller)
    add_photos(offer, 3)
    before = stored()
    response = seller_client.post(edit_url(offer), {**payload(), "photos": [upload(small_jpeg())]})
    assert response.status_code == 200
    assert photos_error(response) == texts.PHOTOS_TOO_MANY.format(max=3)
    assert offer.photos.count() == 3
    assert stored() == before


def test_edit_shows_current_photos_with_remove_box(seller_client, make_offer):
    offer = make_offer(seller_client.seller)
    photos = add_photos(offer, 2)
    doc = parse_html(seller_client.get(edit_url(offer)))
    boxes = doc.find_all("input", name="remove_photos")
    assert [b.get("value") for b in boxes] == [str(p.pk) for p in photos]
    label = next(lab for lab in doc.find_all("label") if lab.get("for") == boxes[0].get("id"))
    assert texts.PHOTO_REMOVE in label.text


def test_remove_and_add_in_the_same_edit(
    seller_client, make_offer, django_capture_on_commit_callbacks
):
    offer = make_offer(seller_client.seller)
    first, second, third = add_photos(offer, 3)
    removed_files = {first.card_image.name, first.page_image.name}
    data = {**payload(), "remove_photos": [first.pk], "photos": [upload(small_jpeg())]}
    with django_capture_on_commit_callbacks(execute=True):
        response = seller_client.post(edit_url(offer), data)
    assert response.status_code == 302
    photos = list(offer.photos.order_by("position"))
    assert [p.position for p in photos] == [0, 1, 2]
    assert [p.pk for p in photos[:2]] == [second.pk, third.pk]
    assert not OfferPhoto.objects.filter(pk=first.pk).exists()
    assert not removed_files & stored()


def test_removing_lets_the_count_go_back_under_the_limit(seller_client, make_offer):
    offer = make_offer(seller_client.seller)
    photos = add_photos(offer, 3)
    data = {**payload(), "remove_photos": [photos[0].pk, photos[1].pk]}
    seller_client.post(edit_url(offer), data)
    assert list(offer.photos.values_list("pk", flat=True)) == [photos[2].pk]
    assert offer.photos.get().position == 0


# Serviço save_offer_photos ----------------------------------------------------------


def test_service_refuses_more_than_three_and_writes_nothing(make_offer):
    offer = make_offer()
    add_photos(offer, 2)
    before = stored()
    with pytest.raises(ValidationError):
        save_offer_photos(offer, [upload(small_jpeg()), upload(small_jpeg())], [])
    assert offer.photos.count() == 2
    assert stored() == before


def test_service_discards_written_files_when_a_later_file_is_invalid(make_offer, fake_jpg_text):
    offer = make_offer()
    before = stored()
    with pytest.raises(ValidationError):
        save_offer_photos(offer, [upload(small_jpeg()), upload(fake_jpg_text)], [])
    assert offer.photos.count() == 0
    assert stored() == before


def test_service_ignores_photo_ids_of_another_offer(make_offer):
    mine, other = make_offer(), make_offer()
    (foreign,) = add_photos(other, 1)
    save_offer_photos(mine, [], [foreign.pk])
    assert OfferPhoto.objects.filter(pk=foreign.pk).exists()


# Limite de envio: 20 arquivos por hora, 12 para vendedor novo (CA14) --------------------


def _user_key(user) -> str:
    request = RequestFactory().post(NEW_URL)
    request.user = user
    return ratelimit.user_key(request)


@time_machine.travel(NOW, tick=False)
def test_upload_limit_per_user_answers_429_and_keeps_the_form(seller_client):
    key = _user_key(seller_client.user)
    ratelimit.register(
        services_seller.PHOTOS_SCOPE, key, services_seller.PHOTOS_WINDOW_S, amount=18
    )
    files = [upload(small_jpeg()) for _ in range(3)]  # 18 + 3 passaria de 20
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 429
    assert response["Retry-After"] == str(services_seller.PHOTOS_WINDOW_S)
    assert photos_error(response) == texts.PHOTOS_RATE_LIMITED
    assert parse_html(response).find("input", name="title").get("value") == "Bolo de pote"
    assert not Offer.objects.exists()

    # Ainda cabem 2 (fecha 20). Depois disso, até sem passar de 3 o envio é recusado.
    files = [upload(small_jpeg()) for _ in range(2)]
    response = seller_client.post(NEW_URL, {**payload(), "photos": files})
    assert response.status_code == 302
    response = seller_client.post(NEW_URL, {**payload(), "photos": [upload(small_jpeg())]})
    assert response.status_code == 429
    # Sem fotos novas, o anúncio salva normalmente.
    assert seller_client.post(NEW_URL, payload()).status_code == 302
    assert Offer.objects.count() == 2


@time_machine.travel(NOW, tick=False)
def test_upload_limit_counts_files_through_the_form(seller_client):
    for _ in range(6):  # 6 × 3 = 18 arquivos
        files = [upload(small_jpeg()) for _ in range(3)]
        assert seller_client.post(NEW_URL, {**payload(), "photos": files}).status_code == 302
    files = [upload(small_jpeg()) for _ in range(3)]
    assert seller_client.post(NEW_URL, {**payload(), "photos": files}).status_code == 429


@time_machine.travel(NOW, tick=False)
def test_untrusted_seller_has_a_lower_upload_limit(make_seller):
    """S1: quem ainda não é confiável envia no máximo 12 arquivos por hora."""
    seller = make_seller(trusted=False)
    client = Client()
    client.force_login(seller.user)
    for _ in range(3):  # 3 × 3 = 9 arquivos, sem passar do teto de 3 pendentes
        files = [upload(small_jpeg()) for _ in range(3)]
        assert client.post(NEW_URL, {**payload(), "photos": files}).status_code == 302
    # Só cabem mais 3: um envio de 3 fecha 12 e a 13ª foto da hora é recusada.
    files = [upload(small_jpeg()) for _ in range(3)]
    assert client.post(NEW_URL, {**payload(title=""), "photos": files}).status_code == 200
    response = client.post(NEW_URL, {**payload(), "photos": [upload(small_jpeg())]})
    assert response.status_code == 429
    assert photos_error(response) == texts.PHOTOS_RATE_LIMITED
    assert Offer.objects.filter(seller=seller).count() == 3


@time_machine.travel(NOW, tick=False)
def test_new_seller_resending_photos_after_form_errors_can_still_publish(make_seller):
    """CA5: reenviar 3 fotos por erro no formulário não trava a primeira publicação."""
    seller = make_seller(trusted=False)
    client = Client()
    client.force_login(seller.user)
    for _ in range(3):
        files = [upload(small_jpeg()) for _ in range(3)]
        assert client.post(NEW_URL, {**payload(title=""), "photos": files}).status_code == 200
    assert not Offer.objects.exists()
    files = [upload(small_jpeg()) for _ in range(3)]
    assert client.post(NEW_URL, {**payload(), "photos": files}).status_code == 302
    assert Offer.objects.get(seller=seller).photos.count() == 3


@time_machine.travel(NOW, tick=False)
def test_new_seller_form_errors_count_and_the_13th_photo_is_refused(make_seller):
    """CA5: 4 envios inválidos de 3 fotos passam; a contagem continua antes de validar."""
    seller = make_seller(trusted=False)
    client = Client()
    client.force_login(seller.user)
    for _ in range(4):  # 4 × 3 = 12 arquivos em formulários com erro
        files = [upload(small_jpeg()) for _ in range(3)]
        assert client.post(NEW_URL, {**payload(title=""), "photos": files}).status_code == 200
    response = client.post(NEW_URL, {**payload(), "photos": [upload(small_jpeg())]})
    assert response.status_code == 429
    assert response["Retry-After"] == str(services_seller.PHOTOS_WINDOW_S)
    assert photos_error(response) == texts.PHOTOS_RATE_LIMITED
    assert not Offer.objects.exists()
    # Sem fotos novas, o anúncio ainda pode ser publicado.
    assert client.post(NEW_URL, payload()).status_code == 302


@time_machine.travel(NOW, tick=False)
def test_trusted_seller_keeps_the_higher_upload_limit(seller_client):
    for _ in range(4):
        files = [upload(small_jpeg()) for _ in range(3)]
        assert seller_client.post(NEW_URL, {**payload(), "photos": files}).status_code == 302
    response = seller_client.post(NEW_URL, {**payload(), "photos": [upload(small_jpeg())]})
    assert response.status_code == 302


@time_machine.travel(NOW, tick=False)
def test_upload_limit_is_per_user(seller_client, other_seller_client):
    key = _user_key(seller_client.user)
    ratelimit.register(
        services_seller.PHOTOS_SCOPE, key, services_seller.PHOTOS_WINDOW_S, amount=20
    )
    response = other_seller_client.post(NEW_URL, {**payload(), "photos": [upload(small_jpeg())]})
    assert response.status_code == 302


def test_csrf_is_enforced_on_upload(seller_client):
    client = Client(enforce_csrf_checks=True)
    client.force_login(seller_client.user)
    response = client.post(NEW_URL, {**payload(), "photos": [upload(make_image_bytes())]})
    assert response.status_code == 403
    assert not OfferPhoto.objects.exists()


def test_photo_limit_race_between_validation_and_save_is_a_form_error(
    seller_client, make_offer, monkeypatch
):
    offer = make_offer(seller_client.seller)
    add_photos(offer, 2)
    real = services_seller.save_offer_photos

    def concurrent(target, files, remove_ids):
        add_photos(target, 1)  # outro envio gravou uma foto no meio do caminho
        return real(target, files, remove_ids)

    monkeypatch.setattr(services_seller, "save_offer_photos", concurrent)
    data = {**payload(title="Mudou"), "photos": [upload(small_jpeg())]}
    response = seller_client.post(edit_url(offer), data)
    assert response.status_code == 200
    assert photos_error(response) == texts.PHOTOS_TOO_MANY.format(max=3)
    offer.refresh_from_db()
    assert offer.title != "Mudou"  # a edição inteira foi desfeita
