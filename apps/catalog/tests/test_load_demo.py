"""CA18: dados de demonstração só com DEMO_DATA, marcados "(exemplo)", idempotentes."""

import io
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.accounts.models import User
from apps.catalog.domain.availability import is_listed, is_page_visible
from apps.catalog.domain.states import PublicState, SellerState, public_state, seller_state
from apps.catalog.models import Offer, OfferPhoto, OfferVariant, Seller
from apps.core import clock

pytestmark = pytest.mark.django_db


def load():
    with override_settings(DEMO_DATA=True):
        call_command("load_demo", stdout=open("/dev/null", "w"))  # noqa: SIM115


def test_refuses_without_demo_data():
    with override_settings(DEMO_DATA=False), pytest.raises(CommandError):
        call_command("load_demo")
    assert not Seller.objects.exists()
    assert not Offer.objects.exists()


def test_marks_everything_as_example():
    load()
    assert Seller.objects.count() >= 3
    for seller in Seller.objects.all():
        assert seller.display_name.endswith("(exemplo)")
        assert seller.is_demo
        assert seller.whatsapp_number == ""
        assert seller.user.email.endswith("@exemplo.invalid")
        assert not seller.user.has_usable_password()
        assert not seller.user.is_staff
    for offer in Offer.objects.all():
        assert offer.title.endswith("(exemplo)")
    assert not OfferPhoto.objects.exists()


def test_is_idempotent():
    load()
    counts = (User.objects.count(), Seller.objects.count(), Offer.objects.count(),
              OfferVariant.objects.count())  # fmt: skip
    slugs = set(Seller.objects.values_list("slug", flat=True))
    load()
    assert (User.objects.count(), Seller.objects.count(), Offer.objects.count(),
            OfferVariant.objects.count()) == counts  # fmt: skip
    assert set(Seller.objects.values_list("slug", flat=True)) == slugs


def test_does_not_touch_real_data(make_seller, make_offer):
    real = make_offer(make_seller(display_name="Maria"), title="Bolo real")
    load()
    real.refresh_from_db()
    assert real.title == "Bolo real"
    assert not real.seller.is_demo


def test_covers_all_kinds_and_states():
    load()
    now, tz = clock.now(), clock.community_tz()
    offers = list(Offer.objects.select_related("seller__user", "category"))
    assert {o.kind for o in offers} == {k.value for k in Offer.Kind}
    assert {o.status for o in offers} == {s.value for s in Offer.Status}
    listed = [o for o in offers if is_listed(o, now, tz, 14, demo_enabled=True)]
    public = {public_state(o, now, tz) for o in listed}
    assert {PublicState.AVAILABLE_TODAY, PublicState.ON_ORDER, PublicState.SOLD_OUT,
            PublicState.SOLD, PublicState.NONE} <= public  # fmt: skip
    seller_states = {seller_state(o, now, tz, 14) for o in offers}
    assert {SellerState.PENDING_APPROVAL, SellerState.HIDDEN, SellerState.PAUSED,
            SellerState.NEEDS_CONFIRMATION} <= seller_states  # fmt: skip


def test_food_with_and_without_ingredients_and_variants():
    load()
    food = Offer.objects.filter(category__is_food=True)
    assert food.exclude(ingredients="").exists()
    assert food.filter(ingredients="").exists()
    assert OfferVariant.objects.exists()
    assert Offer.objects.filter(variants__isnull=False).exclude(price_cents=0).exists()


def test_daily_offer_confirmed_until_1800():
    load()
    now, tz = clock.now(), clock.community_tz()
    daily = Offer.objects.get(kind="daily", closing_time__isnull=False)
    assert daily.daily_confirmed_on == now.astimezone(tz).date()
    assert daily.closing_time.hour == 18


def test_demo_listing_visible_without_whatsapp_number():
    load()
    now, tz = clock.now(), clock.community_tz()
    visible = [o for o in Offer.objects.select_related("seller__user")
               if is_page_visible(o, now, tz, 14, demo_enabled=True)]  # fmt: skip
    assert visible
    titles = {o.title for o in Offer.objects.all()}
    assert any("Cálculo" in t for t in titles)
    assert any("Patinete" in t for t in titles)


def test_rerun_refreshes_expired_demo_dates():
    load()
    Offer.objects.update(
        last_confirmed_at=clock.now() - timedelta(days=90), daily_confirmed_on=None
    )
    load()
    assert Offer.objects.filter(daily_confirmed_on__isnull=False).exists()


def test_remove_deletes_demo_accounts_offers_and_photo_files(
    make_seller, make_offer, make_user, django_capture_on_commit_callbacks
):
    """R3: `load_demo --remove` limpa a demonstração, mesmo com DEMO_DATA desligado."""
    load()
    real = make_offer(make_seller(display_name="Maria"), title="Bolo real")
    # Conta com e-mail do domínio de exemplo, mas sem perfil de demonstração: fica.
    lookalike = make_user(email="alguem@exemplo.invalid")
    demo_offer = Offer.objects.filter(seller__is_demo=True).first()
    photo = OfferPhoto.objects.create(
        offer=demo_offer,
        position=0,
        card_image=ContentFile(b"x", name="c.webp"),
        page_image=ContentFile(b"y", name="p.webp"),
        page_width=10,
        page_height=10,
    )
    names = [photo.card_image.name, photo.page_image.name]
    assert all(default_storage.exists(n) for n in names)

    out = io.StringIO()
    with override_settings(DEMO_DATA=False), django_capture_on_commit_callbacks(execute=True):
        call_command("load_demo", "--remove", stdout=out)

    assert not Seller.objects.filter(is_demo=True).exists()
    assert not User.objects.filter(email__startswith="demo-").exists()
    assert not Offer.objects.filter(title__endswith="(exemplo)").exists()
    assert not OfferPhoto.objects.exists()
    assert not any(default_storage.exists(n) for n in names)
    assert Offer.objects.filter(pk=real.pk).exists()
    assert User.objects.filter(pk=lookalike.pk).exists()
    assert "removidos" in out.getvalue()
    # Rodar de novo não quebra.
    call_command("load_demo", "--remove", stdout=io.StringIO())
