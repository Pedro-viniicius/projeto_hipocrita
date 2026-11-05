"""Filtros para os templates: preço e selo de estado."""

from django import template

from apps.catalog.domain.pricing import format_brl
from apps.catalog.domain.states import StateVM, state_vm

register = template.Library()


@register.filter
def brl(cents) -> str:
    """Centavos em "R$ 12,50"; valor vazio ou inválido vira texto vazio."""
    try:
        return format_brl(int(cents))
    except TypeError, ValueError:
        return ""


@register.filter(name="state_vm")
def state_vm_filter(state) -> StateVM | None:
    """Chave de estado → `StateVM` (rótulo e ícone) ou `None` quando não há selo."""
    return state_vm(state) if state else None
