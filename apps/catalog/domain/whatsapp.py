"""Mensagem e endereço do WhatsApp. O número só entra aqui, no 302 da rota de contato."""

import re
from urllib.parse import quote

from texts import whatsapp as texts


def build_message(title: str, variant: str | None, offer_url: str) -> str:
    """Mensagem pronta; sem variação, só o nome da oferta. O endereço vai em linha própria."""
    if variant:
        text = texts.MESSAGE_WITH_VARIANT.format(title=title, variant=variant)
    else:
        text = texts.MESSAGE.format(title=title)
    if offer_url:
        text += "\n" + texts.MESSAGE_LINK_LINE.format(url=offer_url)
    return text


def build_whatsapp_url(number: str, message: str) -> str:
    """`https://wa.me/<número>?text=<mensagem>`; o número precisa ter só dígitos."""
    if not re.fullmatch(r"\d{10,15}", number or ""):
        raise ValueError("número de WhatsApp inválido")
    return f"https://wa.me/{number}?text={quote(message, safe='')}"
