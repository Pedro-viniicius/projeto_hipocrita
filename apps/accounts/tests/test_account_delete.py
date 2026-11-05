"""Exclusão de conta com senha: tudo sai na hora, numa transação (CA15)."""

import re

import pytest
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.signals import pre_delete
from django.test import Client

from apps.accounts.models import User
from apps.catalog.models import Offer, OfferPhoto, OfferVariant, Seller
from apps.core.testing import assert_accessible_page, parse_html
from apps.metrics.models import DailyOfferStat
from apps.moderation.models import Report
from texts import accounts as texts

pytestmark = pytest.mark.django_db

URL = "/perfil/excluir-conta/"
PASSWORD = "senha-da-conta-123"


@pytest.fixture
def account(make_user, make_seller, make_offer):
    user = make_user(email="ana@exemplo.test", password=PASSWORD)
    seller = make_seller(user=user)
    offer = make_offer(seller, variants=[("Pequeno", 500), ("Grande", 900)])
    make_offer(seller, kind=Offer.Kind.ONE_OFF)
    photo = OfferPhoto(offer=offer, position=0, page_width=10, page_height=10)
    photo.card_image.save("x.webp", ContentFile(b"card"), save=False)
    photo.page_image.save("x.webp", ContentFile(b"page"), save=False)
    photo.save()
    Report.objects.create(offer=offer, reason=Report.Reason.OTHER, details="texto")
    DailyOfferStat.objects.create(date="2026-11-05", offer=offer, views=3)
    client = Client()
    client.force_login(user)
    return {"user": user, "seller": seller, "offer": offer, "photo": photo, "client": client}


def test_requires_login(client):
    response = client.get(URL)
    assert response.status_code == 302
    assert response["Location"].startswith("/entrar/?next=/perfil/excluir-conta/")


def test_confirmation_page(account):
    response = account["client"].get(URL)
    assert response.status_code == 200
    assert_accessible_page(response)
    doc = parse_html(response)
    back = doc.find("a", href="/perfil/")
    danger = doc.find("button", class_="botao--perigo")
    assert back is not None and danger is not None
    # "Voltar, não excluir" vem antes do botão de perigo na ordem do DOM.
    order = [el for el in doc.iter() if el is back or el is danger]
    assert order == [back, danger]
    assert doc.find("input", name="password").get("autocomplete") == "current-password"


def test_wrong_password_deletes_nothing(account):
    response = account["client"].post(URL, {"password": "nao-e-essa"})
    assert response.status_code == 200
    error = parse_html(response).find(id="id_password_error")
    assert error is not None and texts.DELETE_WRONG_PASSWORD in error.text
    assert User.objects.filter(pk=account["user"].pk).exists()
    assert Offer.objects.filter(seller=account["seller"]).count() == 2


def test_delete_removes_everything_and_logs_out(
    account, make_offer, django_capture_on_commit_callbacks
):
    other_offer = make_offer()  # de outro vendedor: não pode ser afetado
    photo = account["photo"]
    names = [photo.card_image.name, photo.page_image.name]
    assert all(default_storage.exists(n) for n in names)
    client = account["client"]

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(URL, {"password": PASSWORD})

    assert response.status_code == 302
    assert response["Location"] == "/"
    assert [str(m) for m in get_messages(response.wsgi_request)] == [texts.ACCOUNT_DELETED]
    assert "_auth_user_id" not in client.session

    # CA15: nada do vendedor sobra para ser exibido.
    assert not User.objects.filter(email="ana@exemplo.test").exists()
    assert not Seller.objects.filter(pk=account["seller"].pk).exists()
    assert not Offer.objects.filter(seller_id=account["seller"].pk).exists()
    assert not OfferVariant.objects.filter(offer_id=account["offer"].pk).exists()
    assert not OfferPhoto.objects.filter(offer_id=account["offer"].pk).exists()
    assert not Report.objects.filter(offer_id=account["offer"].pk).exists()
    assert not DailyOfferStat.objects.filter(offer_id=account["offer"].pk).exists()
    assert not any(default_storage.exists(n) for n in names)
    assert Offer.objects.filter(pk=other_offer.pk).exists()

    # A sessão antiga não vale mais.
    assert client.get(URL).status_code == 302


def test_failed_delete_rolls_back(account):
    """Se algo falhar no meio da cascata, nada é apagado (transação)."""

    def explode(sender, instance, **kwargs):
        raise RuntimeError("falha simulada")

    pre_delete.connect(explode, sender=OfferPhoto, dispatch_uid="teste_explode")
    try:
        with pytest.raises(RuntimeError):
            account["client"].post(URL, {"password": PASSWORD})
    finally:
        pre_delete.disconnect(sender=OfferPhoto, dispatch_uid="teste_explode")
    assert User.objects.filter(pk=account["user"].pk).exists()
    assert Offer.objects.filter(seller=account["seller"]).count() == 2
    assert OfferPhoto.objects.filter(pk=account["photo"].pk).exists()


def test_wrong_password_is_rate_limited(account):
    client = account["client"]
    for _ in range(5):
        assert client.post(URL, {"password": "errada"}).status_code == 200
    blocked = client.post(URL, {"password": PASSWORD})
    assert blocked.status_code == 429
    assert texts.DELETE_RATE_LIMITED in blocked.content.decode()
    assert User.objects.filter(pk=account["user"].pk).exists()


def test_get_does_not_delete(account):
    account["client"].get(URL)
    assert User.objects.filter(pk=account["user"].pk).exists()


def test_csrf_required(account):
    client = Client(enforce_csrf_checks=True)
    client.force_login(account["user"])
    assert client.post(URL, {"password": PASSWORD}).status_code == 403
    assert User.objects.filter(pk=account["user"].pk).exists()
    page = client.get(URL)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    response = client.post(URL, {"password": PASSWORD, "csrfmiddlewaretoken": token.group(1)})
    assert response.status_code == 302
    assert not User.objects.filter(pk=account["user"].pk).exists()
