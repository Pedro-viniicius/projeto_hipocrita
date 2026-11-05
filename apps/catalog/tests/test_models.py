"""Modelos, semente de categorias e remoção de arquivos (CA12, CA13, CA15, CA16)."""

import pytest
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.catalog.models import MAX_PRICE_CENTS, Category, Offer, OfferPhoto, OfferVariant

pytestmark = pytest.mark.django_db


def test_seed_has_five_categories_in_order():
    rows = list(Category.objects.values_list("name", "slug", "is_food", "is_active"))
    assert rows == [
        ("Comidas e doces", "comidas-e-doces", True, True),
        ("Bebidas", "bebidas", True, True),
        ("Serviços", "servicos", False, True),
        ("Objetos e usados", "objetos-e-usados", False, True),
        ("Outros", "outros", False, True),
    ]


def test_user_email_is_lowercase_and_unique():
    user = User.objects.create_user(" Ana@Exemplo.TEST ", "x-senha-123")
    assert user.email == "ana@exemplo.test"
    assert User.objects.get_by_natural_key("ANA@exemplo.test") == user
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("ana@EXEMPLO.test", "outra-senha-123")


def test_superuser_is_staff_and_user_str_has_no_email():
    admin = User.objects.create_superuser("admin@exemplo.test", "senha-admin-123")
    assert admin.is_staff and admin.is_superuser
    assert "admin@" not in str(admin)


def test_user_without_password_cannot_log_in():
    user = User.objects.create_user("demo@exemplo.invalid", None)
    assert not user.has_usable_password()


def test_offer_defaults(make_seller):
    seller = make_seller()
    offer = Offer.objects.create(
        seller=seller,
        category=Category.objects.get(slug="servicos"),
        kind=Offer.Kind.ONE_OFF,
        title="Aula de Cálculo",
        price_cents=3000,
        fulfillment="Biblioteca",
    )
    assert offer.status == Offer.Status.ACTIVE
    assert offer.approval == Offer.Approval.PENDING
    assert offer.last_confirmed_at is not None
    assert offer.status_changed_at is not None
    assert offer.hidden_at is None


@pytest.mark.parametrize("price", [MAX_PRICE_CENTS + 1])
def test_offer_price_limit_enforced_by_database(make_offer, price):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_offer(price_cents=price)


def test_offer_invalid_status_rejected_by_database(make_offer):
    offer = make_offer()
    with pytest.raises(IntegrityError), transaction.atomic():
        Offer.objects.filter(pk=offer.pk).update(status="reserved")


def test_category_with_offers_cannot_be_deleted(make_offer):
    from django.db.models import ProtectedError

    offer = make_offer()
    with pytest.raises(ProtectedError):
        offer.category.delete()


def test_variant_name_unique_per_offer(make_offer):
    offer = make_offer(variants=[("Pequeno", 800)])
    assert list(offer.variants.values_list("name", "price_cents")) == [("Pequeno", 800)]
    with pytest.raises(IntegrityError), transaction.atomic():
        OfferVariant.objects.create(offer=offer, name="Pequeno", price_cents=900)
    make_offer(variants=[("Pequeno", 700)])  # outro anúncio pode repetir o nome


def _photo(offer, position=0):
    photo = OfferPhoto(offer=offer, position=position, page_width=1280, page_height=960)
    photo.card_image.save("qualquer.jpg", ContentFile(b"card"), save=False)
    photo.page_image.save("qualquer.jpg", ContentFile(b"page"), save=False)
    photo.save()
    return photo


def test_photo_names_are_uuid_webp_and_ignore_upload_name(make_offer):
    photo = _photo(make_offer())
    card, page = photo.card_image.name, photo.page_image.name
    assert card.startswith("offers/") and card.endswith("-card.webp")
    assert page == card.replace("-card.webp", "-page.webp")
    assert "qualquer" not in card


def test_photo_position_limits(make_offer):
    offer = make_offer()
    _photo(offer, 0)
    with pytest.raises(IntegrityError), transaction.atomic():
        _photo(offer, 0)
    with pytest.raises(IntegrityError), transaction.atomic():
        _photo(offer, 3)


def test_deleting_photo_removes_files_after_commit(make_offer, django_capture_on_commit_callbacks):
    photo = _photo(make_offer())
    names = [photo.card_image.name, photo.page_image.name]
    with django_capture_on_commit_callbacks(execute=True):
        photo.delete()
    assert not any(default_storage.exists(name) for name in names)


def test_deleting_user_cascades_and_removes_files(
    make_offer, make_seller, django_capture_on_commit_callbacks
):
    seller = make_seller()
    offer = make_offer(seller)
    photo = _photo(offer)
    names = [photo.card_image.name, photo.page_image.name]
    with django_capture_on_commit_callbacks(execute=True):
        seller.user.delete()
    assert not Offer.objects.filter(pk=offer.pk).exists()
    assert not any(default_storage.exists(name) for name in names)


def test_rolled_back_delete_keeps_files(make_offer, django_capture_on_commit_callbacks):
    photo = _photo(make_offer())
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        try:
            with transaction.atomic():
                photo.delete()
                raise RuntimeError("desfaz")
        except RuntimeError:
            pass
    assert callbacks == []
    assert default_storage.exists(photo.card_image.name)


# CA16 e LGPD: tabelas sem identificação de visitante -------------------------

FORBIDDEN_FIELD_PARTS = ("ip", "user_agent", "agent", "cookie", "session", "visitor", "email")


@pytest.mark.parametrize(
    "label", ["metrics.DailyOfferStat", "metrics.DailySearchMiss", "moderation.Report"]
)
def test_metrics_and_reports_store_no_visitor_identity(label):
    model = apps.get_model(label)
    for field in model._meta.get_fields():
        name = field.name.lower()
        parts = name.split("_")
        assert not any(p in parts or p == name for p in FORBIDDEN_FIELD_PARTS), name
    if label.startswith("metrics."):
        # Nenhuma ligação com usuário: só data, oferta e contagens.
        related = {f.related_model for f in model._meta.get_fields() if f.is_relation}
        assert User not in related


def test_ratelimit_counter_has_only_hash():
    model = apps.get_model("core.RateLimitCounter")
    names = {f.name for f in model._meta.get_fields()}
    assert names == {"id", "scope", "key_hash", "window_start", "count"}
