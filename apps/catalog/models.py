"""Modelos do catálogo.

Os rótulos de `choices` ficam aqui (entram nas migrações); o texto mostrado ao
usuário vem de `texts/` (estados em `texts/states.py`, formulários em
`texts/seller.py`), para que editar a cópia não gere migração.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

MAX_PRICE_CENTS = 10_000_000  # R$ 100.000,00


class Category(models.Model):
    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_food = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class Seller(models.Model):
    """Perfil público do vendedor. Contém dado pessoal (LGPD): não registrar em log."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller"
    )
    display_name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=70, unique=True)
    bio = models.CharField(max_length=280, blank=True)
    service_area = models.CharField(max_length=120, blank=True)
    hours = models.CharField(max_length=120, blank=True)
    # Formato 55DD9XXXXXXXX (apps/accounts/phone.py) ou vazio. Nunca vai para HTML.
    whatsapp_number = models.CharField(max_length=13, blank=True)
    whatsapp_public = models.BooleanField(default=False)
    whatsapp_public_changed_at = models.DateTimeField(null=True, blank=True)
    is_trusted = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return f"Vendedor {self.pk}"


class Offer(models.Model):
    class Kind(models.TextChoices):
        RECURRING = "recurring", "Recorrente"
        DAILY = "daily", "Do dia"
        ONE_OFF = "one_off", "Venda pontual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        PAUSED = "paused", "Pausado"
        SOLD_OUT = "sold_out", "Esgotado"
        SOLD = "sold", "Vendido"

    class Approval(models.TextChoices):
        PENDING = "pending", "Aguardando aprovação"
        APPROVED = "approved", "Aprovado"

    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name="offers")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="offers")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    price_cents = models.PositiveIntegerField()
    fulfillment = models.CharField(max_length=100)
    portion = models.CharField(max_length=80, blank=True)
    ingredients = models.CharField(max_length=500, blank=True)
    allergens = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    status_changed_at = models.DateTimeField(default=timezone.now)
    approval = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)
    approved_at = models.DateTimeField(null=True, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=200, blank=True)
    daily_confirmed_on = models.DateField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    last_confirmed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["approval", "status"], name="catalog_offer_appr_status")]
        constraints = [
            models.CheckConstraint(
                condition=Q(price_cents__gte=0) & Q(price_cents__lte=MAX_PRICE_CENTS),
                name="catalog_offer_price_range",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["recurring", "daily", "one_off"]),
                name="catalog_offer_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "paused", "sold_out", "sold"]),
                name="catalog_offer_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(approval__in=["pending", "approved"]),
                name="catalog_offer_approval_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class OfferVariant(models.Model):
    """Variação de preço (no máximo 5 por anúncio; o limite fica no formulário)."""

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=60)
    price_cents = models.PositiveIntegerField()
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["offer", "name"], name="catalog_variant_unique_name"),
            models.CheckConstraint(
                condition=Q(price_cents__gte=0) & Q(price_cents__lte=MAX_PRICE_CENTS),
                name="catalog_variant_price_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name


def _storage_token(instance: OfferPhoto) -> str:
    """Mesmo UUID para os dois tamanhos da mesma foto."""
    token = getattr(instance, "_storage_token", None)
    if not token:
        token = uuid.uuid4().hex
        instance._storage_token = token
    return token


def offer_card_path(instance: OfferPhoto, filename: str) -> str:
    """`offers/<uuid4>-card.webp`; o nome enviado pelo usuário é ignorado."""
    return f"offers/{_storage_token(instance)}-card.webp"


def offer_page_path(instance: OfferPhoto, filename: str) -> str:
    """`offers/<uuid4>-page.webp`; o nome enviado pelo usuário é ignorado."""
    return f"offers/{_storage_token(instance)}-page.webp"


class OfferPhoto(models.Model):
    """Foto já processada (WebP, sem EXIF). Os arquivos somem após o delete (signals.py)."""

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="photos")
    position = models.PositiveSmallIntegerField()
    card_image = models.FileField(upload_to=offer_card_path, max_length=200)
    page_image = models.FileField(upload_to=offer_page_path, max_length=200)
    page_width = models.PositiveSmallIntegerField()
    page_height = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "position"], name="catalog_photo_unique_position"
            ),
            models.CheckConstraint(
                condition=Q(position__lte=2), name="catalog_photo_position_range"
            ),
        ]

    def __str__(self) -> str:
        return f"Foto {self.position} do anúncio {self.offer_id}"
