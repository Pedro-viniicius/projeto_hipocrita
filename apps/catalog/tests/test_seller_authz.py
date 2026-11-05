"""Um vendedor não vê nem altera anúncio ou foto de outro, nem por POST direto (CA11)."""

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict

from apps.catalog.models import Category, Offer, OfferPhoto
from apps.catalog.photos import save_offer_photos
from apps.core.testing import make_image_bytes

pytestmark = pytest.mark.django_db


def snapshot(offer) -> dict:
    """Estado completo do anúncio no banco: campos, variações e fotos."""
    fresh = Offer.objects.get(pk=offer.pk)
    return {
        "offer": model_to_dict(fresh) | {"updated_at": fresh.updated_at},
        "variants": list(fresh.variants.values_list("name", "price_cents", "position")),
        "photos": list(fresh.photos.values_list("pk", "position", "card_image", "page_image")),
    }


def files_exist(photo) -> bool:
    return default_storage.exists(photo.card_image.name) and default_storage.exists(
        photo.page_image.name
    )


@pytest.fixture
def victim_offer(make_offer):
    """Anúncio de outro vendedor, com variação e foto."""
    offer = make_offer(title="Bolo da vizinha", variants=[("Pote", 900)])
    photo = SimpleUploadedFile("a.jpg", make_image_bytes(size=(64, 48)), content_type="image/jpeg")
    save_offer_photos(offer, [photo], [])
    return offer


def offer_payload(**overrides) -> dict:
    data = {
        "kind": "recurring",
        "title": "Tomado",
        "category": Category.objects.get(slug="servicos").pk,
        "price": "1",
        "fulfillment": "Aqui",
    }
    data.update(overrides)
    return data


def test_edit_form_of_another_seller_is_404(seller_client, victim_offer):
    response = seller_client.get(f"/meus-anuncios/{victim_offer.pk}/editar/")
    assert response.status_code == 404
    assert "Bolo da vizinha" not in response.content.decode()


def test_post_edit_of_another_seller_is_404_and_changes_nothing(seller_client, victim_offer):
    before = snapshot(victim_offer)
    photo = victim_offer.photos.get()
    data = offer_payload(remove_photos=[photo.pk])
    response = seller_client.post(f"/meus-anuncios/{victim_offer.pk}/editar/", data)
    assert response.status_code == 404
    assert snapshot(victim_offer) == before
    assert files_exist(photo)


@pytest.mark.parametrize("action", ["pause", "sold_out", "confirm_today", "apagar", ""])
def test_post_action_on_another_sellers_offer_is_404(seller_client, victim_offer, action):
    before = snapshot(victim_offer)
    response = seller_client.post(f"/meus-anuncios/{victim_offer.pk}/acao/", {"action": action})
    assert response.status_code == 404
    assert snapshot(victim_offer) == before


def test_missing_offer_is_404(seller_client):
    assert seller_client.get("/meus-anuncios/999999/editar/").status_code == 404
    response = seller_client.post("/meus-anuncios/999999/acao/", {"action": "pause"})
    assert response.status_code == 404


def test_removing_another_sellers_photo_through_own_offer_does_nothing(
    seller_client, make_offer, victim_offer, django_capture_on_commit_callbacks
):
    mine = make_offer(seller_client.seller)
    foreign = victim_offer.photos.get()
    before = snapshot(victim_offer)
    data = offer_payload(remove_photos=[foreign.pk])
    with django_capture_on_commit_callbacks(execute=True):
        response = seller_client.post(f"/meus-anuncios/{mine.pk}/editar/", data)
    # A foto não pertence a este anúncio: o formulário recusa e nada é gravado.
    assert response.status_code == 200
    assert OfferPhoto.objects.filter(pk=foreign.pk).exists()
    assert files_exist(foreign)
    assert snapshot(victim_offer) == before
    assert Offer.objects.get(pk=mine.pk).title != "Tomado"


def test_anonymous_cannot_act(client, victim_offer):
    before = snapshot(victim_offer)
    response = client.post(f"/meus-anuncios/{victim_offer.pk}/acao/", {"action": "pause"})
    assert response.status_code == 302
    assert response["Location"].startswith("/entrar/")
    response = client.post(f"/meus-anuncios/{victim_offer.pk}/editar/", offer_payload())
    assert response.status_code == 302
    assert snapshot(victim_offer) == before


def test_user_without_seller_profile_is_forbidden(staff_client, victim_offer):
    before = snapshot(victim_offer)
    response = staff_client.post(f"/meus-anuncios/{victim_offer.pk}/acao/", {"action": "pause"})
    assert response.status_code == 403
    response = staff_client.post(f"/meus-anuncios/{victim_offer.pk}/editar/", offer_payload())
    assert response.status_code == 403
    assert snapshot(victim_offer) == before


def test_owner_still_can_edit(other_seller_client, make_offer):
    # Controle: o mesmo pedido feito pelo dono funciona.
    offer = make_offer(other_seller_client.seller)
    response = other_seller_client.post(f"/meus-anuncios/{offer.pk}/editar/", offer_payload())
    assert response.status_code == 302
    assert Offer.objects.get(pk=offer.pk).title == "Tomado"
