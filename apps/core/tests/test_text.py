import pytest

from apps.catalog.models import Category, Seller
from apps.core.text import unique_slug

pytestmark = pytest.mark.django_db


def test_slug_without_accents():
    assert unique_slug(Seller, "Pão de Queijo da Lú") == "pao-de-queijo-da-lu"


def test_slug_gets_numeric_suffix_when_taken(make_seller):
    make_seller(display_name="Doces da Ana", slug="doces-da-ana")
    make_seller(display_name="Doces da Ana 2", slug="doces-da-ana-2")
    assert unique_slug(Seller, "Doces da Ana") == "doces-da-ana-3"


def test_slug_fallback_when_no_letters():
    assert unique_slug(Seller, "!!! ???", fallback="vendedor") == "vendedor"
    assert unique_slug(Seller, "") == "item"


def test_slug_respects_max_length_with_suffix(make_seller):
    long_name = "a" * 100
    first = unique_slug(Seller, long_name)
    assert len(first) == 70
    make_seller(slug=first)
    second = unique_slug(Seller, long_name)
    assert second.endswith("-2")
    assert len(second) == 70


def test_slug_ignores_own_row_when_renaming():
    category = Category.objects.get(slug="bebidas")
    assert unique_slug(Category, "Bebidas", exclude_pk=category.pk) == "bebidas"
    assert unique_slug(Category, "Bebidas") == "bebidas-2"
