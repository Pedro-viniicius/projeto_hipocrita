"""Rodízio com semente da data (CA17)."""

from datetime import date
from types import SimpleNamespace

from apps.catalog.domain.ordering import order_offers, shuffle_key

DAY = date(2026, 11, 5)


def items(n=30, tier=None):
    return [(tier, SimpleNamespace(pk=i)) for i in range(1, n + 1)]


def pks(offers):
    return [o.pk for o in offers]


def test_shuffle_key_is_stable_and_depends_on_day():
    assert shuffle_key(DAY, 7) == shuffle_key(DAY, 7)
    assert shuffle_key(DAY, 7) != shuffle_key(date(2026, 11, 6), 7)
    assert shuffle_key(DAY, 7) != shuffle_key(DAY, 8)


def test_same_day_same_order_regardless_of_input_order():
    a = pks(order_offers(items(), DAY))
    b = pks(order_offers(list(reversed(items())), DAY))
    assert a == b
    assert sorted(a) == list(range(1, 31))


def test_order_changes_next_day():
    assert pks(order_offers(items(), DAY)) != pks(order_offers(items(), date(2026, 11, 6)))


def test_compatible_first_by_tier_then_shuffle():
    data = [(2, SimpleNamespace(pk=1)), (0, SimpleNamespace(pk=2)), (1, SimpleNamespace(pk=3)),
            (0, SimpleNamespace(pk=4))]  # fmt: skip
    result = pks(order_offers(data, DAY))
    assert result[2:] == [3, 1]
    assert set(result[:2]) == {2, 4}
    expected = sorted([2, 4], key=lambda pk: shuffle_key(DAY, pk))
    assert result[:2] == expected


def test_ignores_popularity_attributes():
    popular = [(None, SimpleNamespace(pk=i, clicks=1000 - i, views=i * 9)) for i in range(1, 21)]
    plain = [(None, SimpleNamespace(pk=i)) for i in range(1, 21)]
    assert pks(order_offers(popular, DAY)) == pks(order_offers(plain, DAY))


def test_empty():
    assert order_offers([], DAY) == []
