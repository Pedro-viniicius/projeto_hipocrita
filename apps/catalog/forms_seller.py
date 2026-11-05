"""Formulários da área do vendedor: anúncio (CA8, CA13) e perfil (CA6).

O servidor sempre ignora os campos que não valem para o tipo ou a categoria
escolhidos (D20): o valor some de `cleaned_data` e um erro neles não impede o
envio. Nada aqui registra telefone ou outro dado pessoal em log.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.text import slugify

from apps.accounts.phone import format_br_mobile, normalize_br_mobile
from apps.catalog.domain.actions import confirmation_refusal
from apps.catalog.domain.availability import is_available_today
from apps.catalog.domain.pricing import parse_brl
from apps.catalog.imaging import validate_image
from apps.catalog.models import MAX_PRICE_CENTS, Category, Offer, OfferVariant, Seller
from apps.catalog.photos import too_many_photos_error
from texts import seller as texts

VARIANT_ROWS = 5
DAILY_ONLY_FIELDS = ("closing_time", "confirm_today")
FOOD_ONLY_FIELDS = ("portion", "ingredients", "allergens")
PHOTO_ACCEPT = "image/jpeg,image/png,image/webp"
WHATSAPP_MAX_LENGTH = 30

REQUIRED_MESSAGES = {"required": texts.REQUIRED}


def _max_length(model, name: str) -> int:
    return model._meta.get_field(name).max_length


def _text_field(label: str, help_text: str, max_length: int, *, required=True, textarea=False):
    widget = forms.Textarea(attrs={"rows": 3}) if textarea else forms.TextInput()
    return forms.CharField(
        label=label,
        help_text=help_text,
        max_length=max_length,
        required=required,
        error_messages=REQUIRED_MESSAGES,
        widget=widget,
    )


def _price_field(label: str, help_text: str, *, required=True) -> forms.CharField:
    return forms.CharField(
        label=label,
        help_text=help_text,
        max_length=20,
        required=required,
        error_messages={"required": texts.REQUIRED, "max_length": texts.PRICE_INVALID},
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
    )


def _clean_price(raw: str) -> int:
    try:
        cents = parse_brl(raw)
    except ValueError:
        raise ValidationError(texts.PRICE_INVALID, code="invalid") from None
    if cents > MAX_PRICE_CENTS:
        raise ValidationError(texts.PRICE_TOO_HIGH, code="max_value")
    return cents


def _format_price(cents: int) -> str:
    reais, centavos = divmod(cents, 100)
    return f"{reais},{centavos:02d}"


class NoLabelSuffixMixin:
    """Rótulo sem ":" e a lista de campos com erro para o resumo no topo."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    @property
    def fields_with_errors(self) -> list:
        return [field for field in self if field.errors]


class CategorySelect(forms.Select):
    """Select de categoria: opção de alimento leva `data-food` (o CSS usa com `:has()`)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None and instance.is_food:
            option["attrs"]["data-food"] = True
        return option


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class PhotosField(forms.FileField):
    """Várias fotos num campo só. Cada arquivo é validado pelo conteúdo (`imaging`)."""

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = [f for f in (data or []) if f]
        if not files and self.required:
            raise ValidationError(self.error_messages["required"], code="required")
        return files


class OfferForm(NoLabelSuffixMixin, forms.Form):
    """Criar e editar anúncio. `offer` é o anúncio em edição (ou `None`)."""

    kind = forms.ChoiceField(
        label=texts.KIND_LABEL,
        choices=[(k, v) for k, v in texts.KIND_CHOICES.items()],
        widget=forms.RadioSelect,
        error_messages={"required": texts.CHOICE_INVALID, "invalid_choice": texts.CHOICE_INVALID},
    )
    title = _text_field(texts.TITLE_LABEL, texts.TITLE_HELP, _max_length(Offer, "title"))
    category = forms.ModelChoiceField(
        label=texts.CATEGORY_LABEL,
        queryset=Category.objects.none(),
        empty_label=texts.CATEGORY_EMPTY,
        widget=CategorySelect,
        error_messages={"required": texts.CHOICE_INVALID, "invalid_choice": texts.CHOICE_INVALID},
    )
    price = _price_field(texts.PRICE_LABEL, texts.PRICE_HELP)
    description = _text_field(
        texts.DESCRIPTION_LABEL,
        texts.DESCRIPTION_HELP,
        _max_length(Offer, "description"),
        required=False,
        textarea=True,
    )
    fulfillment = _text_field(
        texts.FULFILLMENT_LABEL, texts.FULFILLMENT_HELP, _max_length(Offer, "fulfillment")
    )
    photos = PhotosField(
        label=texts.PHOTOS_LABEL,
        required=False,
        widget=MultipleFileInput(attrs={"accept": PHOTO_ACCEPT, "multiple": True}),
    )
    remove_photos = forms.TypedMultipleChoiceField(
        label=texts.PHOTO_REMOVE,
        coerce=int,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"invalid_choice": texts.PHOTO_REMOVE_INVALID},
    )
    closing_time = forms.TimeField(
        label=texts.CLOSING_LABEL,
        help_text=texts.CLOSING_HELP,
        required=False,
        input_formats=["%H:%M", "%H:%M:%S", "%Hh%M", "%Hh"],
        error_messages={"invalid": texts.TIME_INVALID},
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    confirm_today = forms.BooleanField(label=texts.CONFIRM_TODAY_LABEL, required=False)
    portion = _text_field(
        texts.PORTION_LABEL, texts.PORTION_HELP, _max_length(Offer, "portion"), required=False
    )
    ingredients = _text_field(
        texts.INGREDIENTS_LABEL,
        texts.INGREDIENTS_HELP,
        _max_length(Offer, "ingredients"),
        required=False,
        textarea=True,
    )
    allergens = _text_field(
        texts.ALLERGENS_LABEL,
        texts.ALLERGENS_HELP,
        _max_length(Offer, "allergens"),
        required=False,
        textarea=True,
    )

    def __init__(
        self,
        *args,
        offer: Offer | None = None,
        now: datetime,
        tz: ZoneInfo,
        photos_blocked: bool = False,
        **kwargs,
    ):
        self.offer = offer
        self.now = now
        self.tz = tz
        self.photos_blocked = photos_blocked
        self.current_photos = list(offer.photos.order_by("position", "pk")) if offer else []
        if offer is not None and "initial" not in kwargs:
            kwargs["initial"] = self._initial_from(offer)
        kwargs.setdefault("initial", {"confirm_today": True})
        super().__init__(*args, **kwargs)

        # Categoria inativa só aparece se já é a deste anúncio (editar não quebra).
        active = Q(is_active=True)
        if offer is not None:
            active |= Q(pk=offer.category_id)
        self.fields["category"].queryset = Category.objects.filter(active).order_by(
            "position", "name"
        )
        self.fields["photos"].help_text = texts.PHOTOS_HELP.format(mb=settings.MAX_UPLOAD_MB)
        self.fields["remove_photos"].choices = [(p.pk, str(p.pk)) for p in self.current_photos]

        for n in range(VARIANT_ROWS):
            name_field = _text_field(
                texts.VARIANT_NAME_LABEL.format(n=n + 1),
                texts.VARIANT_NAME_HELP if n == 0 else "",
                _max_length(OfferVariant, "name"),
                required=False,
            )
            price_field = _price_field(
                texts.VARIANT_PRICE_LABEL.format(n=n + 1),
                texts.VARIANT_PRICE_HELP if n == 0 else "",
                required=False,
            )
            self.fields[f"variant_name_{n}"] = name_field
            self.fields[f"variant_price_{n}"] = price_field

    def _initial_from(self, offer: Offer) -> dict:
        initial = {
            "kind": offer.kind,
            "title": offer.title,
            "category": offer.category_id,
            "price": _format_price(offer.price_cents),
            "description": offer.description,
            "fulfillment": offer.fulfillment,
            "closing_time": offer.closing_time,
            "confirm_today": offer.kind != Offer.Kind.DAILY
            or is_available_today(offer.daily_confirmed_on, offer.closing_time, self.now, self.tz),
            "portion": offer.portion,
            "ingredients": offer.ingredients,
            "allergens": offer.allergens,
        }
        for n, variant in enumerate(offer.variants.order_by("position", "pk")[:VARIANT_ROWS]):
            initial[f"variant_name_{n}"] = variant.name
            initial[f"variant_price_{n}"] = _format_price(variant.price_cents)
        return initial

    # Linhas para o template ----------------------------------------------------

    @property
    def variant_rows(self) -> list[tuple]:
        return [
            (self[f"variant_name_{n}"], self[f"variant_price_{n}"]) for n in range(VARIANT_ROWS)
        ]

    @property
    def kind_options(self) -> list[dict]:
        """Opções do tipo com dica, para o template montar os cartões `.opcao`."""
        current = str(self["kind"].value() or "")
        return [
            {
                "value": value,
                "label": label,
                "help": texts.KIND_HELP[value].format(dias=settings.RECONFIRM_DAYS),
                "id": f"id_kind_{index}",
                "checked": current == value,
            }
            for index, (value, label) in enumerate(texts.KIND_CHOICES.items())
        ]

    @property
    def photo_items(self) -> list[dict]:
        """Fotos atuais com a caixa "Remover esta foto" (marcada se veio marcada)."""
        marked = {str(v) for v in (self["remove_photos"].value() or [])}
        return [
            {"photo": photo, "number": index + 1, "checked": str(photo.pk) in marked}
            for index, photo in enumerate(self.current_photos)
        ]

    # Validação -----------------------------------------------------------------

    def clean_title(self) -> str:
        return " ".join(self.cleaned_data["title"].split())

    def clean_price(self) -> int:
        return _clean_price(self.cleaned_data["price"])

    def clean_photos(self) -> list:
        files = self.cleaned_data["photos"]
        if not files:
            return []
        if self.photos_blocked:
            raise ValidationError(texts.PHOTOS_RATE_LIMITED, code="rate_limited")
        if len(files) > settings.MAX_PHOTOS_PER_OFFER:
            raise too_many_photos_error()
        errors = []
        for upload in files:
            try:
                validate_image(upload)
            except ValidationError as exc:
                errors.extend(exc.error_list)
        if errors:
            # Mesma mensagem uma vez só, mesmo com vários arquivos ruins.
            unique = {e.message: e for e in errors}
            raise ValidationError(list(unique.values()))
        return files

    def _drop(self, names: tuple[str, ...], empty: dict) -> None:
        """Ignora campos que não valem: tira o erro e zera o valor."""
        for name in names:
            self._errors.pop(name, None)
            self.cleaned_data[name] = empty[name]

    def _clean_variants(self) -> list[tuple[str, int]]:
        variants: list[tuple[str, int]] = []
        seen: set[str] = set()
        for n in range(VARIANT_ROWS):
            name_key, price_key = f"variant_name_{n}", f"variant_price_{n}"
            if name_key in self._errors or price_key in self._errors:
                continue
            name = " ".join((self.cleaned_data.get(name_key) or "").split())
            raw_price = (self.cleaned_data.get(price_key) or "").strip()
            if not name and not raw_price:
                continue
            if not name:
                self.add_error(name_key, ValidationError(texts.VARIANT_NAME_MISSING))
                continue
            if not raw_price:
                self.add_error(price_key, ValidationError(texts.VARIANT_PRICE_MISSING))
                continue
            try:
                cents = _clean_price(raw_price)
            except ValidationError as exc:
                self.add_error(price_key, exc)
                continue
            if name.casefold() in seen:
                self.add_error(name_key, ValidationError(texts.VARIANT_NAME_REPEATED))
                continue
            seen.add(name.casefold())
            variants.append((name, cents))
        return variants

    def _check_photo_total(self) -> None:
        files = self.cleaned_data.get("photos") or []
        if not files or "photos" in self._errors:
            return
        removing = set(self.cleaned_data.get("remove_photos") or [])
        kept = [p for p in self.current_photos if p.pk not in removing]
        if len(kept) + len(files) > settings.MAX_PHOTOS_PER_OFFER:
            self.add_error("photos", too_many_photos_error())

    def _check_confirmation(self) -> None:
        """Confirmar hoje com o encerramento já passado ou a partir de 23:59 é recusado
        (CA9). A regra é a mesma do botão (`domain.actions.confirmation_refusal`)."""
        if not self.cleaned_data.get("confirm_today") or "closing_time" in self._errors:
            return
        refusal = confirmation_refusal(self.cleaned_data.get("closing_time"), self.now, self.tz)
        if refusal == "closing_passed":
            self.add_error("closing_time", ValidationError(texts.CLOSING_PASSED))
        elif refusal is not None:
            self.add_error("confirm_today", ValidationError(texts.CONFIRM_DAY_OVER))

    def clean(self) -> dict:
        data = super().clean()
        kind = data.get("kind")
        category = data.get("category")
        if kind and kind != Offer.Kind.DAILY:
            self._drop(DAILY_ONLY_FIELDS, {"closing_time": None, "confirm_today": False})
        if self.offer is not None and self.offer.hidden_at is not None:
            # Anúncio oculto pela administração não pode ser confirmado: a caixa é ignorada.
            self._drop(("confirm_today",), {"confirm_today": False})
        if category is not None and not category.is_food:
            self._drop(FOOD_ONLY_FIELDS, {"portion": "", "ingredients": "", "allergens": ""})
        if kind == Offer.Kind.DAILY:
            self._check_confirmation()
        data["variants"] = self._clean_variants()
        self._check_photo_total()
        return data


class ProfileForm(NoLabelSuffixMixin, forms.Form):
    """Dados públicos do vendedor, WhatsApp e autorização para mostrar o número (CA6)."""

    display_name = _text_field(
        texts.NAME_LABEL, texts.NAME_HELP, _max_length(Seller, "display_name")
    )
    bio = _text_field(
        texts.BIO_LABEL, texts.BIO_HELP, _max_length(Seller, "bio"), required=False, textarea=True
    )
    service_area = _text_field(
        texts.AREA_LABEL, texts.AREA_HELP, _max_length(Seller, "service_area"), required=False
    )
    hours = _text_field(
        texts.HOURS_LABEL, texts.HOURS_HELP, _max_length(Seller, "hours"), required=False
    )
    whatsapp = forms.CharField(
        label=texts.WHATSAPP_LABEL,
        help_text=texts.WHATSAPP_HELP,
        max_length=WHATSAPP_MAX_LENGTH,
        error_messages={"required": texts.REQUIRED, "max_length": texts.WHATSAPP_INVALID},
        widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel"}),
    )
    whatsapp_public = forms.TypedChoiceField(
        label=texts.WHATSAPP_PUBLIC_LABEL,
        help_text=texts.WHATSAPP_PUBLIC_HELP,
        choices=[("sim", texts.WHATSAPP_PUBLIC_YES), ("nao", texts.WHATSAPP_PUBLIC_NO)],
        coerce=lambda value: value == "sim",
        widget=forms.RadioSelect,
        error_messages={"required": texts.CHOICE_INVALID, "invalid_choice": texts.CHOICE_INVALID},
    )

    def __init__(self, *args, seller: Seller, **kwargs):
        self.seller = seller
        kwargs.setdefault(
            "initial",
            {
                "display_name": seller.display_name,
                "bio": seller.bio,
                "service_area": seller.service_area,
                "hours": seller.hours,
                "whatsapp": format_br_mobile(seller.whatsapp_number)
                if seller.whatsapp_number
                else "",
                "whatsapp_public": "sim" if seller.whatsapp_public else "nao",
            },
        )
        super().__init__(*args, **kwargs)

    def clean_display_name(self) -> str:
        name = " ".join(self.cleaned_data["display_name"].split())
        if not slugify(name):
            raise ValidationError(texts.NAME_INVALID, code="invalid")
        return name

    def clean_whatsapp(self) -> str:
        number = normalize_br_mobile(self.cleaned_data["whatsapp"])
        if number is None:
            raise ValidationError(texts.WHATSAPP_INVALID, code="invalid")
        return number
