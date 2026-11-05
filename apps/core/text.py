"""Utilidades de texto que dependem do banco (as puras de busca ficam em catalog/domain)."""

from django.db import models
from django.utils.text import slugify


def unique_slug(
    model: type[models.Model],
    value: str,
    *,
    field: str = "slug",
    fallback: str = "item",
    exclude_pk: int | None = None,
) -> str:
    """Slug ASCII único para `model.<field>`, com sufixo -2, -3… quando já existe.

    Acentos viram letras simples ("Pão" → "pao"). Texto sem letras usa `fallback`.
    Respeita o `max_length` do campo, cortando a base para caber o sufixo.
    `exclude_pk` ignora a própria linha ao renomear.
    """
    max_length = model._meta.get_field(field).max_length or 50
    base = slugify(value)[:max_length].strip("-") or slugify(fallback) or "item"
    qs = model._default_manager.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)

    candidate = base
    suffix = 1
    while qs.filter(**{field: candidate}).exists():
        suffix += 1
        tail = f"-{suffix}"
        candidate = f"{base[: max_length - len(tail)].rstrip('-')}{tail}"
    return candidate
