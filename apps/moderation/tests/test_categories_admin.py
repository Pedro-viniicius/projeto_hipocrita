"""Categorias no admin (CA12): criar, renomear, posição, visibilidade e alimento; sem excluir."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.catalog.models import Category
from apps.core.testing import assert_accessible_page, parse_html
from texts import moderation as texts

SEED = ["Comidas e doces", "Bebidas", "Serviços", "Objetos e usados", "Outros"]


def _messages(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def _update(client, category, **data):
    payload = {
        "action": data.pop("action", "save"),
        f"cat-{category.pk}-name": data.pop("name", category.name),
        f"cat-{category.pk}-position": data.pop("position", category.position),
    }
    if data.pop("is_food", category.is_food):
        payload[f"cat-{category.pk}-is_food"] = "on"
    assert not data
    return client.post(reverse("moderation:category_update", args=[category.pk]), payload)


def test_list_shows_every_category_with_forms(staff_client):
    Category.objects.filter(slug="outros").update(is_active=False)
    response = staff_client.get(reverse("moderation:categories"))
    assert response.status_code == 200
    html = response.content.decode()
    for name in SEED:
        assert name in html
    assert "Escondida" in html
    doc = parse_html(response)
    for category in Category.objects.all():
        assert doc.find("form", action=reverse("moderation:category_update", args=[category.pk]))
    assert doc.find("input", name="nova-name") is not None
    assert_accessible_page(response)


def test_create_category_goes_to_the_end(staff_client):
    last = max(Category.objects.values_list("position", flat=True))
    response = staff_client.post(
        reverse("moderation:categories"),
        {"nova-name": "  Livros   e apostilas ", "nova-position": ""},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("moderation:categories")
    category = Category.objects.get(name="Livros e apostilas")
    assert category.slug == "livros-e-apostilas"
    assert category.position == last + 1
    assert category.is_active is True
    assert category.is_food is False
    assert texts.CATEGORY_CREATED in _messages(response)


def test_create_category_with_position_and_food(staff_client):
    staff_client.post(
        reverse("moderation:categories"),
        {"nova-name": "Marmitas", "nova-position": "0", "nova-is_food": "on"},
    )
    category = Category.objects.get(name="Marmitas")
    assert category.position == 0
    assert category.is_food is True


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("bebidas", texts.CATEGORY_NAME_TAKEN),
        ("SERVIÇOS", texts.CATEGORY_NAME_TAKEN),
        ("", texts.CATEGORY_REQUIRED),
        ("---", texts.CATEGORY_NAME_INVALID),
    ],
)
def test_create_invalid_name_is_refused(staff_client, name, error):
    before = Category.objects.count()
    response = staff_client.post(reverse("moderation:categories"), {"nova-name": name})
    assert response.status_code == 400
    assert error in response.content.decode()
    assert Category.objects.count() == before
    assert_accessible_page(response)


@pytest.mark.parametrize("position", ["-1", "1000", "abc"])
def test_invalid_position_is_refused(staff_client, position):
    response = staff_client.post(
        reverse("moderation:categories"), {"nova-name": "Livros", "nova-position": position}
    )
    assert response.status_code == 400
    assert texts.CATEGORY_POSITION_INVALID in response.content.decode()
    assert not Category.objects.filter(name="Livros").exists()


def test_rename_reorder_and_mark_food_keeps_slug(staff_client):
    category = Category.objects.get(slug="servicos")
    response = _update(staff_client, category, name="Aulas e serviços", position=0, is_food=True)
    assert response.status_code == 302
    category.refresh_from_db()
    assert category.name == "Aulas e serviços"
    assert category.position == 0
    assert category.is_food is True
    assert category.slug == "servicos"  # links já compartilhados continuam valendo
    assert texts.SAVED in _messages(response)


def test_unmark_food(staff_client):
    category = Category.objects.get(slug="bebidas")
    assert category.is_food is True
    _update(staff_client, category, is_food=False)
    category.refresh_from_db()
    assert category.is_food is False


def test_rename_to_existing_name_is_refused(staff_client):
    category = Category.objects.get(slug="servicos")
    response = _update(staff_client, category, name="Bebidas")
    assert response.status_code == 400
    assert texts.CATEGORY_NAME_TAKEN in response.content.decode()
    category.refresh_from_db()
    assert category.name == "Serviços"
    assert_accessible_page(response)


def test_keeping_own_name_is_allowed(staff_client):
    category = Category.objects.get(slug="servicos")
    response = _update(staff_client, category, position=42)
    assert response.status_code == 302
    category.refresh_from_db()
    assert category.position == 42


def test_position_defines_chip_order(staff_client):
    outros = Category.objects.get(slug="outros")
    comidas = Category.objects.get(slug="comidas-e-doces")
    _update(staff_client, outros, position=0)
    _update(staff_client, comidas, position=50)
    names = list(Category.objects.filter(is_active=True).values_list("name", flat=True))
    assert names[0] == "Outros"
    assert names[-1] == "Comidas e doces"

    page = staff_client.get(reverse("moderation:categories")).content.decode()
    assert page.index("Outros ·") < page.index("Comidas e doces ·")


def test_hide_and_show_category(staff_client):
    category = Category.objects.get(slug="outros")
    response = _update(staff_client, category, action="hide", name="ignorado")
    assert response.status_code == 302
    category.refresh_from_db()
    assert category.is_active is False
    assert category.name == "Outros"  # esconder não salva os outros campos
    assert texts.CATEGORY_HIDDEN in _messages(response)

    response = _update(staff_client, category, action="show")
    category.refresh_from_db()
    assert category.is_active is True
    assert texts.CATEGORY_SHOWN in _messages(response)


def test_categories_cannot_be_deleted(staff_client):
    category = Category.objects.get(slug="outros")
    before = Category.objects.count()
    response = _update(staff_client, category, action="delete")
    assert response.status_code == 400
    url = reverse("moderation:category_update", args=[category.pk])
    assert staff_client.delete(url).status_code == 405
    assert Category.objects.count() == before
    page = staff_client.get(reverse("moderation:categories")).content.decode()
    assert "Excluir" not in page
