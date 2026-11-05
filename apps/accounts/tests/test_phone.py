"""Celular brasileiro do WhatsApp (CA6, D5)."""

import pytest

from apps.accounts.phone import VALID_DDDS, format_br_mobile, normalize_br_mobile


def test_there_are_67_ddds():
    assert len(VALID_DDDS) == 67
    assert {11, 35, 61, 99} <= VALID_DDDS
    assert not {10, 20, 23, 25, 26, 29, 30, 36, 39, 40, 50, 52, 56, 70, 72, 76, 78, 80, 90} & (
        VALID_DDDS
    )


@pytest.mark.parametrize(
    "raw",
    [
        "(35) 91234-5678",
        "35912345678",
        "35 9 1234 5678",
        "35 91234 5678",
        "+55 35 91234-5678",
        "+55 (35) 9 1234-5678",
        "5535912345678",
        "035912345678",
        "0 35 91234-5678",
        "0055 35 91234 5678",
        " (35)91234.5678 ",
    ],
)
def test_accepts_common_formats(raw):
    assert normalize_br_mobile(raw) == "5535912345678"


def test_ddd_55_is_not_confused_with_country_code():
    assert normalize_br_mobile("(55) 91234-5678") == "5555912345678"
    assert normalize_br_mobile("+55 55 91234-5678") == "5555912345678"
    assert normalize_br_mobile("55912345678") == "5555912345678"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "abc",
        "(35) 3821-1234",  # fixo
        "(35) 33821-1234",  # 9 dígitos sem começar com 9
        "(20) 91234-5678",  # DDD inexistente
        "(00) 91234-5678",
        "(35) 9123-4567",  # curto
        "(35) 912345-6789",  # longo
        "+1 35 91234-5678",
        "5535912345678" * 4,  # texto colado
    ],
)
def test_rejects_invalid_numbers(raw):
    assert normalize_br_mobile(raw) is None


def test_rejects_none_safely():
    assert normalize_br_mobile(None) is None  # type: ignore[arg-type]


def test_format():
    assert format_br_mobile("5535912345678") == "(35) 91234-5678"
    assert format_br_mobile("35912345678") == "(35) 91234-5678"
    assert format_br_mobile("123") == "123"
