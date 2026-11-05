"""Formatação e leitura de preço."""

import pytest

from apps.catalog.domain.pricing import display_price, format_brl, parse_brl


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "R$ 0,00"),
        (5, "R$ 0,05"),
        (1250, "R$ 12,50"),
        (125000, "R$ 1.250,00"),
        (10_000_000, "R$ 100.000,00"),
    ],
)
def test_format_brl(cents, text):
    assert format_brl(cents) == text


def test_format_brl_negative():
    with pytest.raises(ValueError):
        format_brl(-1)


@pytest.mark.parametrize(
    ("raw", "cents"),
    [
        ("8,5", 850),
        ("8,50", 850),
        ("R$ 8,50", 850),
        ("r$8,50", 850),
        ("8.50", 850),
        ("8", 800),
        ("0,99", 99),
        ("1.250,00", 125000),
        ("1.250", 125000),
        ("1250", 125000),
        (" 12 ", 1200),
        ("1,250.50", None),
    ],
)
def test_parse_brl(raw, cents):
    if cents is None:
        with pytest.raises(ValueError):
            parse_brl(raw)
    else:
        assert parse_brl(raw) == cents


@pytest.mark.parametrize(
    "raw", ["", "  ", "abc", "-5", "-5,00", "8,505", "1,2,3", "1.2.3", ",5", "R$", "8,5x"]
)
def test_parse_brl_invalid(raw):
    with pytest.raises(ValueError):
        parse_brl(raw)


def test_display_price():
    assert display_price(1000, []) == (1000, False)
    assert display_price(1000, [1000, 1000]) == (1000, False)
    assert display_price(1000, [1200, 1500]) == (1000, True)
    assert display_price(1500, [1200, 1000]) == (1000, True)


def test_brl_filter():
    from apps.catalog.templatetags.catalog_ui import brl, state_vm_filter

    assert brl(1250) == "R$ 12,50"
    assert brl("1250") == "R$ 12,50"
    assert brl(None) == ""
    assert brl("x") == ""
    assert state_vm_filter("sold").label == "Vendido"
    assert state_vm_filter("none") is None
    assert state_vm_filter("") is None
