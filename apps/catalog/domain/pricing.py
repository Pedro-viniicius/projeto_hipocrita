"""Preço em reais, sem depender do locale do sistema."""

import re

_AMOUNT = re.compile(r"\d+")


def format_brl(cents: int) -> str:
    """1250 → "R$ 12,50"; 125000 → "R$ 1.250,00"."""
    if cents < 0:
        raise ValueError("preço negativo")
    reais, centavos = divmod(cents, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def parse_brl(raw: str) -> int:
    """ "8,5", "8,50", "R$ 8,50", "8.50" e "1.250,00" → centavos. `ValueError` se inválido."""
    text = re.sub(r"\s+", "", re.sub(r"(?i)r\$", "", raw or ""))
    if not text or not re.fullmatch(r"[\d.,]+", text):
        raise ValueError("preço inválido")
    if "," in text:
        whole, _, frac = text.rpartition(",")
        if "," in whole or (frac and not _AMOUNT.fullmatch(frac)) or len(frac) > 2:
            raise ValueError("preço inválido")
        groups = whole.split(".")
    elif text.count(".") == 1 and len(text.split(".")[1]) in (1, 2):
        whole, _, frac = text.partition(".")
        groups = [whole]
    else:  # só pontos: separador de milhar ("1.250") ou nada
        whole, frac, groups = text, "", text.split(".")
    if not groups[0] or (len(groups) > 1 and not all(len(g) == 3 for g in groups[1:])):
        raise ValueError("preço inválido")
    if not all(g.isdigit() for g in groups):
        raise ValueError("preço inválido")
    reais = int("".join(groups))
    return reais * 100 + int(frac.ljust(2, "0")) if frac else reais * 100


def display_price(base_cents: int, variant_cents: list[int]) -> tuple[int, bool]:
    """(centavos, é "A partir de"). A base conta como opção; só há "A partir de" se diferem."""
    prices = [base_cents, *variant_cents]
    lowest = min(prices)
    return lowest, len(set(prices)) > 1
