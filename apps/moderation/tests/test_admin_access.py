"""Acesso à administração (CA12): tudo sob `staff_required`; mutação só por POST com CSRF."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.catalog.models import Category, Offer
from apps.core.testing import assert_accessible_page
from apps.moderation.models import Report


@pytest.fixture
def objects(make_offer, make_seller):
    offer = make_offer(make_seller(trusted=False), approval=Offer.Approval.PENDING)
    report = Report.objects.create(offer=offer, reason=Report.Reason.OTHER, details="texto")
    category = Category.objects.get(slug="bebidas")
    return {"offer": offer, "report": report, "category": category}


GET_ROUTES = [
    ("moderation:approvals", None),
    ("moderation:offers", None),
    ("moderation:offer_preview", "offer"),
    ("moderation:reports", None),
    ("moderation:categories", None),
    ("metrics:dashboard", None),
]

POST_ROUTES = [
    ("moderation:offer_approve", "offer"),
    ("moderation:offer_hide", "offer"),
    ("moderation:offer_show", "offer"),
    ("moderation:report_resolve", "report"),
    ("moderation:categories", None),
    ("moderation:category_update", "category"),
]


def _url(name: str, key: str | None, objects: dict) -> str:
    return reverse(name, args=[objects[key].pk]) if key else reverse(name)


def _snapshot(objects: dict) -> tuple:
    offer = Offer.objects.get(pk=objects["offer"].pk)
    report = Report.objects.get(pk=objects["report"].pk)
    category = Category.objects.get(pk=objects["category"].pk)
    return (
        offer.approval,
        offer.hidden_at,
        offer.seller.is_trusted,
        report.status,
        category.is_active,
        category.name,
        Category.objects.count(),
    )


@pytest.mark.parametrize(("name", "key"), GET_ROUTES + POST_ROUTES)
def test_anonymous_goes_to_login(client, objects, name, key):
    url = _url(name, key, objects)
    for method in (client.get, client.post):
        response = method(url)
        assert response.status_code == 302
        assert response["Location"].startswith(reverse("accounts:login"))


@pytest.mark.parametrize(("name", "key"), GET_ROUTES + POST_ROUTES)
def test_seller_gets_403_and_nothing_changes(seller_client, objects, name, key):
    before = _snapshot(objects)
    url = _url(name, key, objects)
    assert seller_client.get(url).status_code == 403
    response = seller_client.post(
        url, {"hide": "1", "action": "hide", "nova-name": "Livros", "cat-1-name": "X"}
    )
    assert response.status_code == 403
    assert _snapshot(objects) == before


@pytest.mark.parametrize(("name", "key"), GET_ROUTES)
def test_staff_sees_every_page(staff_client, objects, name, key):
    response = staff_client.get(_url(name, key, objects))
    assert response.status_code == 200
    assert_accessible_page(response)
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize(
    ("name", "key"),
    [route for route in POST_ROUTES if route[0] != "moderation:categories"],
)
def test_staff_mutations_reject_get(staff_client, objects, name, key):
    before = _snapshot(objects)
    assert staff_client.get(_url(name, key, objects)).status_code == 405
    assert _snapshot(objects) == before


@pytest.mark.parametrize(
    ("name", "key", "data"),
    [
        ("moderation:offer_approve", "offer", {}),
        ("moderation:offer_hide", "offer", {"reason": "teste"}),
        ("moderation:offer_show", "offer", {}),
        ("moderation:report_resolve", "report", {"hide": "1"}),
        ("moderation:categories", None, {"nova-name": "Livros", "nova-position": "9"}),
        ("moderation:category_update", "category", {"action": "hide"}),
    ],
)
def test_staff_post_redirects(staff_client, objects, name, key, data):
    response = staff_client.post(_url(name, key, objects), data)
    assert response.status_code == 302


@pytest.mark.parametrize(("name", "key"), POST_ROUTES)
def test_post_without_csrf_token_is_refused(make_user, objects, name, key):
    client = Client(enforce_csrf_checks=True)
    client.force_login(make_user(is_staff=True))
    before = _snapshot(objects)
    response = client.post(
        _url(name, key, objects), {"hide": "1", "action": "hide", "nova-name": "Livros"}
    )
    assert response.status_code == 403
    assert _snapshot(objects) == before


def test_inactive_staff_is_not_admin(make_user, objects):
    """Admin desativado perde o acesso (a sessão deixa de valer)."""
    user = make_user(is_staff=True)
    client = Client()
    client.force_login(user)
    user.is_active = False
    user.save(update_fields=["is_active"])
    response = client.get(reverse("moderation:approvals"))
    assert response.status_code in {302, 403}


def test_unknown_ids_give_404(staff_client):
    for name in ("moderation:offer_approve", "moderation:offer_hide", "moderation:offer_show"):
        assert staff_client.post(reverse(name, args=[999999])).status_code == 404
    assert staff_client.get(reverse("moderation:offer_preview", args=[999999])).status_code == 404
    assert staff_client.post(reverse("moderation:report_resolve", args=[999999])).status_code == 404
    response = staff_client.post(reverse("moderation:category_update", args=[999999]))
    assert response.status_code == 404


def test_header_links_to_admin_for_staff(staff_client):
    response = staff_client.get(reverse("moderation:approvals"))
    assert reverse("moderation:approvals") in response.content.decode()
    assert reverse("metrics:dashboard") in response.content.decode()
