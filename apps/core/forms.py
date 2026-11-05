"""Formulários acessíveis.

O Django 5.2 já marca `aria-invalid="true"` no campo com erro e aponta
`aria-describedby` para `<id>_helptext` e `<id>_error` (conferido em
`django/forms/boundfield.py`, `build_widget_attrs` e `aria_describedby`), e a
lista de erros sai com `id="<id>_error"`. Aqui só expomos esses ids para o
template `django/forms/field.html` do designer e ligamos o renderer do projeto,
que procura os templates de formulário primeiro em `templates/`.
"""

from django.forms.boundfield import BoundField
from django.forms.renderers import TemplatesSetting


class AccessibleBoundField(BoundField):
    @property
    def helptext_id(self) -> str:
        """Id do elemento da dica (`<id>_helptext`), ou vazio sem `auto_id`."""
        return f"{self.auto_id}_helptext" if self.auto_id else ""

    @property
    def error_id(self) -> str:
        """Id da lista de erros (`<id>_error`), ou vazio sem `auto_id`."""
        return f"{self.auto_id}_error" if self.auto_id else ""


class AccessibleFormRenderer(TemplatesSetting):
    """Renderer padrão (`FORM_RENDERER`): usa os templates do projeto e o BoundField acima."""

    bound_field_class = AccessibleBoundField
