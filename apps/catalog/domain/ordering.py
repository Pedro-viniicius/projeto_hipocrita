"""Rodízio da lista (CA17): compatíveis primeiro; entre iguais, semente da data, nunca cliques."""

import hashlib
from datetime import date


def shuffle_key(day: date, offer_id: int) -> str:
    """Chave estável no dia e diferente no dia seguinte."""
    return hashlib.sha256(f"{day.isoformat()}:{offer_id}".encode()).hexdigest()


def order_offers(items: list[tuple[int | None, object]], day: date) -> list:
    """Ordena `(tier, oferta)` por `(tier, shuffle_key)`. `tier=None` (sem busca) vale 0."""
    ranked = sorted(
        items,
        key=lambda item: (item[0] or 0, shuffle_key(day, item[1].pk), item[1].pk),
    )
    return [offer for _, offer in ranked]
