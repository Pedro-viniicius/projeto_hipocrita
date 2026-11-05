"""Mensagem e endereço do WhatsApp (base de CA1 e CA6)."""

from urllib.parse import parse_qs, urlparse

import pytest

from apps.catalog.domain.whatsapp import build_message, build_whatsapp_url

URL = "https://exemplo.test/oferta/7/"


def test_message_without_variant():
    msg = build_message("Brownie", None, URL)
    assert msg.splitlines()[0] == "Oi! Vi “Brownie” no Pão de Cada Dia. Ainda está disponível?"
    assert msg.splitlines()[1] == URL


def test_message_with_variant():
    msg = build_message("Brownie", "Com nozes", URL)
    assert msg.startswith(
        "Oi! Vi “Brownie”, opção “Com nozes” no Pão de Cada Dia. Ainda está disponível?"
    )


def test_message_without_link():
    assert "\n" not in build_message("Brownie", "", "")


def test_url_encodes_message():
    msg = build_message("Pão & café #1", "50%", URL)
    link = build_whatsapp_url("5535912345678", msg)
    parts = urlparse(link)
    assert (parts.scheme, parts.netloc, parts.path) == ("https", "wa.me", "/5535912345678")
    assert parse_qs(parts.query)["text"] == [msg]
    assert "&" not in parts.query.replace("%26", "")
    assert " " not in link
    assert "\n" not in link


@pytest.mark.parametrize(
    "number", ["", "abc", "55 35 91234-5678", "../x", "5535912345678/../a", "123"]
)
def test_url_rejects_bad_number(number):
    with pytest.raises(ValueError):
        build_whatsapp_url(number, "oi")
