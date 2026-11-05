"""Fixtures compartilhadas por todas as etapas.

Congelado na etapa 1: mudanças passam pelo lead. As fábricas criam dados
válidos e publicáveis por padrão (vendedor confiável com WhatsApp autorizado,
anúncio aprovado e ativo); cada teste muda só o que importa para ele.
"""

import itertools
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.test import Client

from apps.core.testing import make_image_bytes

DEFAULT_PASSWORD = "senha-de-teste-123"
DEFAULT_WHATSAPP = "5535912345678"
DEFAULT_CATEGORY_SLUG = "comidas-e-doces"

_seq = itertools.count(1)


@pytest.fixture
def tz() -> ZoneInfo:
    """Fuso da comunidade (America/Sao_Paulo nos testes)."""
    return ZoneInfo(settings.COMMUNITY_TZ)


@pytest.fixture
def make_user(db):
    """`make_user(email=None, password=DEFAULT_PASSWORD, **campos) -> User`."""
    from apps.accounts.models import User

    def factory(email: str | None = None, password: str = DEFAULT_PASSWORD, **fields):
        email = email or f"pessoa{next(_seq)}@exemplo.test"
        return User.objects.create_user(email=email, password=password, **fields)

    return factory


@pytest.fixture
def make_seller(db, make_user):
    """`make_seller(user=None, *, trusted=True, whatsapp_public=True, **campos) -> Seller`.

    O número padrão é `DEFAULT_WHATSAPP` ("5535912345678"); passe
    `whatsapp_number=""` para vendedor sem número.
    """
    from apps.catalog.models import Seller
    from apps.core.text import unique_slug

    def factory(user=None, *, trusted: bool = True, whatsapp_public: bool = True, **fields):
        user = user or make_user()
        display_name = fields.pop("display_name", f"Vendedor {next(_seq)}")
        fields.setdefault("whatsapp_number", DEFAULT_WHATSAPP)
        fields.setdefault("slug", unique_slug(Seller, display_name, fallback="vendedor"))
        return Seller.objects.create(
            user=user,
            display_name=display_name,
            is_trusted=trusted,
            whatsapp_public=whatsapp_public,
            **fields,
        )

    return factory


@pytest.fixture
def make_offer(db, make_seller):
    """`make_offer(seller=None, *, kind="recurring", category=None, variants=(), **campos)`.

    Por padrão: aprovado, ativo, R$ 10,00, categoria "Comidas e doces".
    `category` aceita um `Category` ou um slug. `variants` é uma lista de
    `(nome, preço_em_centavos)`.
    """
    from apps.catalog.models import Category, Offer, OfferVariant

    def factory(seller=None, *, kind: str = Offer.Kind.RECURRING, category=None, variants=(), **f):
        seller = seller or make_seller()
        if category is None or isinstance(category, str):
            category = Category.objects.get(slug=category or DEFAULT_CATEGORY_SLUG)
        f.setdefault("title", f"Oferta {next(_seq)}")
        f.setdefault("price_cents", 1000)
        f.setdefault("fulfillment", "Retirada no campus")
        f.setdefault("status", Offer.Status.ACTIVE)
        f.setdefault("approval", Offer.Approval.APPROVED)
        offer = Offer.objects.create(seller=seller, category=category, kind=kind, **f)
        for position, (name, price_cents) in enumerate(variants):
            OfferVariant.objects.create(
                offer=offer, name=name, price_cents=price_cents, position=position
            )
        return offer

    return factory


def _logged_client(user, **attrs) -> Client:
    client = Client()
    client.force_login(user)
    client.user = user
    for name, value in attrs.items():
        setattr(client, name, value)
    return client


@pytest.fixture
def seller_client(make_seller) -> Client:
    """Cliente logado como vendedor; `client.user` e `client.seller` disponíveis."""
    seller = make_seller()
    return _logged_client(seller.user, seller=seller)


@pytest.fixture
def other_seller_client(make_seller) -> Client:
    """Outro vendedor, para testes de autorização (CA11)."""
    seller = make_seller()
    return _logged_client(seller.user, seller=seller)


@pytest.fixture
def staff_client(make_user) -> Client:
    """Cliente logado como administrador (`is_staff`, sem perfil de vendedor)."""
    user = make_user(is_staff=True)
    return _logged_client(user)


@pytest.fixture
def jpeg_bytes() -> bytes:
    """JPEG 800×600 válido, com EXIF (marca da câmera, orientação 6 e GPS)."""
    return make_image_bytes("JPEG", (800, 600), exif=True)


@pytest.fixture
def png_bytes() -> bytes:
    """PNG 640×480 válido (use com nome `.jpg` para testar o tipo real)."""
    return make_image_bytes("PNG", (640, 480))


@pytest.fixture
def fake_jpg_text() -> bytes:
    """Texto puro para enviar com nome `.jpg` e `content_type` de imagem."""
    return b"isto nao e uma imagem, so texto com extensao .jpg\n" * 20
