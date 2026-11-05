"""Os helpers de `apps/core/testing.py` acusam o que devem acusar."""

import io

import pytest
from django.http import HttpResponse
from PIL import Image, UnidentifiedImageError

from apps.core import testing as t

GOOD = """<!doctype html><html lang="pt-BR"><body><main id="conteudo">
<h1>Título</h1>
<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="x">
<label for="id_q">Busca</label><input id="id_q" name="q">
<button type="submit">Ir</button></form>
<article id="oferta-1"><a href="/oferta/1/"><img src="a.webp" alt=""> Bolo</a></article>
<script src="/static/js/share.js"></script>
</main></body></html>"""


def test_good_page_passes():
    t.assert_accessible_page(GOOD)
    t.assert_single_link_per_article(GOOD)
    t.assert_phone_absent(GOOD, "5535912345678")


@pytest.mark.parametrize(
    ("check", "html"),
    [
        (t.assert_lang_pt_br, GOOD.replace('lang="pt-BR"', 'lang="en"')),
        (t.assert_single_h1, GOOD.replace("<h1>Título</h1>", "<h1>A</h1><h1>B</h1>")),
        (t.assert_main_landmark, GOOD.replace('<main id="conteudo">', "<main>")),
        (t.assert_fields_have_labels, GOOD.replace('<label for="id_q">Busca</label>', "")),
        (
            t.assert_fields_have_labels,
            GOOD.replace('<label for="id_q">Busca</label>', '<label for="id_q"></label>'),
        ),  # noqa: E501
        (t.assert_images_have_alt, GOOD.replace(' alt=""', "")),
        (t.assert_unique_ids, GOOD.replace('id="oferta-1"', 'id="id_q"')),
        (t.assert_no_inline_code, GOOD.replace("<h1>", '<h1 style="color:red">')),
        (t.assert_no_inline_code, GOOD.replace("</main>", "<script>alert(1)</script></main>")),
        (t.assert_no_inline_code, GOOD.replace("<button", '<button onclick="x()"')),
        (t.assert_post_forms_have_csrf, GOOD.replace('name="csrfmiddlewaretoken"', 'name="x"')),
        (t.assert_single_link_per_article, GOOD.replace(" Bolo</a>", '</a><a href="/v/">V</a>')),
    ],
)
def test_bad_pages_fail(check, html):
    with pytest.raises(AssertionError):
        check(html)


@pytest.mark.parametrize(
    "shown", ["5535912345678", "35912345678", "(35) 91234-5678", "91234-5678", "912345678"]
)
def test_phone_absent_catches_common_formats(shown):
    with pytest.raises(AssertionError):
        t.assert_phone_absent(f"<p>Fale: {shown}</p>", "5535912345678")


def test_no_set_cookie():
    response = HttpResponse("ok")
    t.assert_no_set_cookie(response)
    response.set_cookie("sessionid", "x")
    with pytest.raises(AssertionError):
        t.assert_no_set_cookie(response)


def test_parse_and_find():
    doc = t.parse_html(GOOD)
    article = doc.find("article", id="oferta-1")
    assert article.text == "Bolo"
    assert doc.find("input", name="q").get("id") == "id_q"
    assert [a.get("href") for a in doc.find_all("a")] == ["/oferta/1/"]


def test_make_image_bytes_formats_and_exif():
    jpeg = Image.open(io.BytesIO(t.make_image_bytes("JPEG", (40, 30), exif=True)))
    assert jpeg.format == "JPEG"
    assert jpeg.size == (40, 30)
    exif = jpeg.getexif()
    assert exif[0x0112] == 6  # orientação
    assert exif.get_ifd(0x8825)  # GPS presente
    png = Image.open(io.BytesIO(t.make_image_bytes("PNG", (10, 10))))
    assert png.format == "PNG"


def test_fixtures_images(jpeg_bytes, png_bytes, fake_jpg_text):
    assert jpeg_bytes[:3] == b"\xff\xd8\xff"
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(UnidentifiedImageError):
        Image.open(io.BytesIO(fake_jpg_text))
