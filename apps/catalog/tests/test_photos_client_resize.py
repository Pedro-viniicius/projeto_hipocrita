"""Redução das fotos no navegador (`static/js/fotos.js`): o que o servidor entrega à página.

O JS em si não roda aqui; estes testes provam o contrato com o HTML: o limite em
`data-max-mb`, o script externo (CSP), os textos fora do JS e a página sem código inline.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings as django_settings

from apps.core.testing import assert_no_inline_code, parse_html
from texts import seller as texts

pytestmark = pytest.mark.django_db

NEW_URL = "/meus-anuncios/novo/"
SCRIPT = Path(django_settings.BASE_DIR) / "static" / "js" / "fotos.js"


def photos_input(response):
    return parse_html(response).find("input", name="photos")


def test_photos_input_carries_the_server_limit(seller_client, settings):
    settings.MAX_UPLOAD_MB = 1
    field = photos_input(seller_client.get(NEW_URL))
    assert field.get("type") == "file"
    assert field.get("data-max-mb") == "1"


@pytest.mark.parametrize("mb", [1, 5])
def test_data_max_mb_follows_max_upload_mb(seller_client, settings, mb):
    settings.MAX_UPLOAD_MB = mb
    assert photos_input(seller_client.get(NEW_URL)).get("data-max-mb") == str(mb)


def test_edit_form_also_carries_the_limit(seller_client, make_offer, settings):
    settings.MAX_UPLOAD_MB = 1
    offer = make_offer(seller=seller_client.seller)
    field = photos_input(seller_client.get(f"/meus-anuncios/{offer.pk}/editar/"))
    assert field.get("data-max-mb") == "1"


@pytest.mark.parametrize("max_photos", [1, 3, 5])
def test_data_max_photos_follows_max_photos_per_offer(seller_client, settings, max_photos):
    # R6: o JS lê do HTML quantas fotos cabem, em vez de um número fixo no script.
    settings.MAX_PHOTOS_PER_OFFER = max_photos
    assert photos_input(seller_client.get(NEW_URL)).get("data-max-photos") == str(max_photos)


def test_edit_form_also_carries_the_photo_count(seller_client, make_offer):
    offer = make_offer(seller=seller_client.seller)
    field = photos_input(seller_client.get(f"/meus-anuncios/{offer.pk}/editar/"))
    assert field.get("data-max-photos") == str(django_settings.MAX_PHOTOS_PER_OFFER)


def test_only_the_photos_input_gets_the_limit(seller_client):
    doc = parse_html(seller_client.get(NEW_URL))
    marked = [el for el in doc.iter() if el.has("data-max-mb")]
    assert [el.get("name") for el in marked] == ["photos"]


def test_page_includes_the_script_as_external_file(seller_client):
    response = seller_client.get(NEW_URL)
    scripts = [s.get("src") for s in parse_html(response).find_all("script")]
    assert any(src and src.endswith("js/fotos.js") for src in scripts)
    # O enhance.js continua incluído: o bloqueio do JS novo convive com o "Enviando…".
    assert any(src and src.endswith("js/enhance.js") for src in scripts)


def test_page_has_no_inline_code(seller_client):
    assert_no_inline_code(seller_client.get(NEW_URL))


def test_notices_come_from_the_template_hidden_by_default(seller_client):
    doc = parse_html(seller_client.get(NEW_URL))
    (status,) = [el for el in doc.iter() if el.has("data-fotos-status")]
    (warning,) = [el for el in doc.iter() if el.has("data-fotos-aviso")]
    assert status.has("hidden") and status.text.strip() == texts.PHOTOS_PROCESSING
    assert warning.has("hidden") and warning.get("role") == "alert"
    assert texts.PHOTOS_TOTAL_TOO_BIG in warning.text


def test_help_text_mentions_the_limit_and_the_reduction(seller_client, settings):
    settings.MAX_UPLOAD_MB = 1
    doc = parse_html(seller_client.get(NEW_URL))
    help_text = doc.find(id="id_photos_helptext").text
    assert "o site tenta diminuí-las antes de enviar" in help_text
    assert "de até 1 MB cada" in help_text


def test_script_has_no_user_visible_text_of_its_own():
    # Os textos vêm do template; o script só mostra e esconde os elementos.
    source = SCRIPT.read_text(encoding="utf-8")
    assert texts.PHOTOS_TOTAL_TOO_BIG not in source
    assert texts.PHOTOS_PROCESSING not in source
    assert "data-max-mb" in source
    # R6: o máximo de fotos vem do HTML, não de um número fixo no script.
    assert "data-max-photos" in source
    assert not re.search(r"MAX_PHOTOS\s*=", source)


def test_script_processes_one_photo_at_a_time_and_honours_exif():
    # R3 e orientação EXIF (contrato do código; o comportamento foi conferido no Chrome).
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Promise.all" not in source
    assert 'imageOrientation: "from-image"' in source
    # R2: só a restauração do bfcache refaz a conta, a partir das fotos do campo.
    assert "event.persisted" in source
    assert 'new Event("change"' in source
