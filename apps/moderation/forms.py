"""Formulários da administração: motivo de ocultar e categorias."""

import re

from django import forms

from apps.catalog.models import Category
from texts import moderation as texts

CATEGORY_NAME_MAX = 40
POSITION_MAX = 999
HIDE_REASON_MAX = 200


class _AdminForm(forms.Form):
    """Rótulos sem ":" e lista de campos com erro para o resumo no topo."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    @property
    def fields_with_errors(self) -> list:
        return [field for field in self if field.errors]


class HideOfferForm(_AdminForm):
    reason = forms.CharField(
        label=texts.HIDE_REASON_LABEL,
        help_text=texts.HIDE_REASON_HELP,
        required=False,
        max_length=HIDE_REASON_MAX,
        error_messages={"max_length": texts.HIDE_REASON_TOO_LONG},
    )


def _position_field(required: bool) -> forms.IntegerField:
    return forms.IntegerField(
        label=texts.CATEGORY_POSITION_LABEL,
        help_text=texts.CATEGORY_POSITION_HELP,
        required=required,
        min_value=0,
        max_value=POSITION_MAX,
        error_messages={
            "required": texts.CATEGORY_REQUIRED,
            "invalid": texts.CATEGORY_POSITION_INVALID,
            "min_value": texts.CATEGORY_POSITION_INVALID,
            "max_value": texts.CATEGORY_POSITION_INVALID,
        },
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )


class CategoryForm(_AdminForm):
    """Criar (posição opcional: vai para o fim) ou editar uma categoria. Não há excluir."""

    name = forms.CharField(
        label=texts.CATEGORY_NAME_LABEL,
        max_length=CATEGORY_NAME_MAX,
        error_messages={"required": texts.CATEGORY_REQUIRED},
    )
    position = _position_field(required=True)
    is_food = forms.BooleanField(label=texts.CATEGORY_IS_FOOD_LABEL, required=False)

    def __init__(self, *args, instance: Category | None = None, **kwargs):
        self.instance = instance
        if instance is not None:
            kwargs.setdefault(
                "initial",
                {"name": instance.name, "position": instance.position, "is_food": instance.is_food},
            )
        super().__init__(*args, **kwargs)
        if instance is None:
            self.fields["name"].help_text = texts.CATEGORY_NAME_HELP
            self.fields["position"] = _position_field(required=False)

    def clean_name(self) -> str:
        name = re.sub(r"\s+", " ", self.cleaned_data["name"]).strip()
        if not any(ch.isalnum() for ch in name):
            raise forms.ValidationError(texts.CATEGORY_NAME_INVALID)
        others = Category.objects.all()
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        # Poucas categorias: comparar em Python vale para maiúsculas com acento também.
        wanted = name.casefold()
        if any(other.casefold() == wanted for other in others.values_list("name", flat=True)):
            raise forms.ValidationError(texts.CATEGORY_NAME_TAKEN)
        return name
