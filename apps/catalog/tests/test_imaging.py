"""Validação do tipo real e do tamanho; dois tamanhos em WebP sem metadados (CA13)."""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog import imaging
from apps.catalog.imaging import Processed, process_image, validate_image
from apps.core.testing import make_image_bytes
from texts import photos as texts

MB = 1024 * 1024


def upload(data: bytes, name: str = "foto.jpg", content_type: str = "image/jpeg"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def image_bytes(img: Image.Image, fmt: str, **kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def open_webp(content) -> Image.Image:
    content.seek(0)
    img = Image.open(io.BytesIO(content.read()))
    img.load()
    return img


def assert_clean_webp(content) -> Image.Image:
    img = open_webp(content)
    assert img.format == "WEBP"
    assert not {"exif", "xmp", "icc_profile"} & set(img.info)
    assert len(img.getexif()) == 0
    return img


# Validação ---------------------------------------------------------------------


def test_real_jpeg_is_accepted(jpeg_bytes):
    f = upload(jpeg_bytes)
    validate_image(f)
    assert f.tell() == 0  # o arquivo volta ao início para o processamento


def test_png_renamed_jpg_is_accepted_by_content(png_bytes):
    validate_image(upload(png_bytes, "foto.jpg", "image/jpeg"))


def test_webp_is_accepted():
    validate_image(upload(make_image_bytes("WEBP", (300, 200)), "foto.webp", "image/webp"))


def test_text_renamed_jpg_is_rejected(fake_jpg_text):
    with pytest.raises(ValidationError) as exc:
        validate_image(upload(fake_jpg_text))
    assert exc.value.code == "invalid_image"
    assert exc.value.messages == [texts.PHOTO_INVALID]


@pytest.mark.parametrize("fmt", ["GIF", "BMP", "TIFF"])
def test_other_real_image_formats_are_rejected(fmt):
    data = image_bytes(Image.new("RGB", (50, 50)), fmt)
    with pytest.raises(ValidationError) as exc:
        validate_image(upload(data, "foto.jpg"))
    assert exc.value.code == "invalid_image"


def test_svg_is_rejected():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(ValidationError):
        validate_image(upload(svg, "foto.svg", "image/svg+xml"))


def test_empty_file_is_rejected():
    with pytest.raises(ValidationError):
        validate_image(upload(b""))


def test_more_than_5_mb_is_rejected():
    data = make_image_bytes("PNG", (1400, 1400), noise=True)
    assert len(data) > 5 * MB
    with pytest.raises(ValidationError) as exc:
        validate_image(upload(data, "foto.png", "image/png"))
    assert exc.value.code == "too_large"
    assert exc.value.messages == [texts.PHOTO_TOO_LARGE.format(mb=5)]


def test_limit_follows_setting(settings):
    settings.MAX_UPLOAD_MB = 1
    data = make_image_bytes("PNG", (800, 800), noise=True)
    assert MB < len(data) < 5 * MB
    with pytest.raises(ValidationError) as exc:
        validate_image(upload(data, "foto.png"))
    assert exc.value.code == "too_large"


def test_more_than_24_megapixels_is_rejected():
    # 1 bit por pixel: 24,006 MP comprimem para poucos KB (bomba de descompressão).
    data = image_bytes(Image.new("1", (6000, 4001)), "PNG")
    assert len(data) < MB
    with pytest.raises(ValidationError) as exc:
        validate_image(upload(data, "foto.png"))
    assert exc.value.code == "too_many_pixels"
    with pytest.raises(ValidationError) as exc:
        process_image(upload(data, "foto.png"))
    assert exc.value.code == "too_many_pixels"


def test_24_megapixels_is_accepted():
    data = image_bytes(Image.new("1", (6000, 4000)), "PNG")
    validate_image(upload(data, "foto.png"))


def test_decompression_bomb_is_rejected():
    data = image_bytes(Image.new("1", (10000, 10000)), "PNG")  # 100 MP
    with pytest.raises(ValidationError):
        validate_image(upload(data, "foto.png"))


def test_truncated_jpeg_is_rejected(jpeg_bytes):
    f = upload(jpeg_bytes[: len(jpeg_bytes) // 2])
    with pytest.raises(ValidationError):
        validate_image(f)
        process_image(f)


def test_corrupted_png_is_rejected(png_bytes):
    corrupted = png_bytes[:60] + b"\x00" * 40 + png_bytes[100:]
    with pytest.raises(ValidationError):
        validate_image(upload(corrupted, "foto.png"))


# Processamento -----------------------------------------------------------------


def test_process_generates_two_webp_sizes_without_exif(jpeg_bytes):
    assert b"CameraTeste" in jpeg_bytes  # a fixture tem EXIF e GPS
    f = upload(jpeg_bytes)
    validate_image(f)
    result = process_image(f)
    assert isinstance(result, Processed)

    card = assert_clean_webp(result.card)
    assert card.size == (480, 480)
    page = assert_clean_webp(result.page)
    # Orientação 6: o 800×600 original fica em pé (600×800).
    assert page.size == (600, 800)
    assert (result.width, result.height) == (600, 800)

    for content in (result.card, result.page):
        content.seek(0)
        raw = content.read()
        assert b"CameraTeste" not in raw
        assert b"Exif" not in raw
    assert result.card.name.endswith(".webp")
    assert result.page.name.endswith(".webp")


def test_page_is_limited_to_1280_on_longest_side():
    data = make_image_bytes("JPEG", (2560, 1000))
    result = process_image(upload(data))
    assert (result.width, result.height) == (1280, 500)
    assert open_webp(result.page).size == (1280, 500)
    assert open_webp(result.card).size == (480, 480)


def test_small_image_is_not_enlarged_on_page():
    result = process_image(upload(make_image_bytes("PNG", (200, 100)), "foto.png"))
    assert (result.width, result.height) == (200, 100)
    assert open_webp(result.card).size == (480, 480)


def test_card_is_center_crop():
    # Faixa vermelha no centro de uma imagem larga: o corte central fica todo vermelho.
    img = Image.new("RGB", (1500, 500), (0, 0, 255))
    img.paste((255, 0, 0), (500, 0, 1000, 500))
    result = process_image(upload(image_bytes(img, "PNG"), "foto.png"))
    card = open_webp(result.card).convert("RGB")
    for xy in [(5, 5), (240, 240), (474, 474)]:
        r, g, b = card.getpixel(xy)
        assert r > 200 and b < 60


def test_transparent_png_and_palette_images():
    rgba = Image.new("RGBA", (300, 300), (255, 0, 0, 0))
    result = process_image(upload(image_bytes(rgba, "PNG"), "foto.png"))
    assert open_webp(result.page).mode == "RGBA"
    palette = Image.new("P", (300, 300))
    result = process_image(upload(image_bytes(palette, "PNG"), "foto.png"))
    assert_clean_webp(result.card)
    cmyk = Image.new("CMYK", (300, 300))
    result = process_image(upload(image_bytes(cmyk, "JPEG"), "foto.jpg"))
    assert open_webp(result.page).mode == "RGB"


def _decoded_sizes(monkeypatch) -> list[tuple[int, int]]:
    """Tamanhos com que o JPEG foi decodificado (o que vai para a memória)."""
    sizes: list[tuple[int, int]] = []
    original = imaging.ImageOps.exif_transpose

    def spy(img, **kwargs):
        sizes.append(img.size)
        return original(img, **kwargs)

    monkeypatch.setattr(imaging.ImageOps, "exif_transpose", spy)
    return sizes


def test_big_jpeg_is_decoded_reduced(monkeypatch):
    # S1: o JPEG é decodificado já reduzido (DCT), sem passar de 1280 nos dois lados.
    sizes = _decoded_sizes(monkeypatch)
    result = process_image(upload(make_image_bytes("JPEG", (4000, 3000))))
    assert sizes == [(2000, 1500)]
    assert (result.width, result.height) == (1280, 960)
    assert open_webp(result.card).size == (480, 480)


def test_reduced_decode_keeps_exif_rotation(monkeypatch):
    sizes = _decoded_sizes(monkeypatch)
    result = process_image(upload(make_image_bytes("JPEG", (4000, 3000), exif=True)))
    assert sizes == [(2000, 1500)]
    assert (result.width, result.height) == (960, 1280)
    assert_clean_webp(result.page)


def test_small_jpeg_is_decoded_full_size(monkeypatch):
    sizes = _decoded_sizes(monkeypatch)
    process_image(upload(make_image_bytes("JPEG", (2000, 1500))))
    assert sizes == [(2000, 1500)]


def test_png_is_not_reduced_before_decoding(monkeypatch):
    sizes = _decoded_sizes(monkeypatch)
    result = process_image(upload(make_image_bytes("PNG", (3000, 2000)), "foto.png"))
    assert sizes == [(3000, 2000)]
    assert (result.width, result.height) == (1280, 853)


def test_process_rejects_non_image(fake_jpg_text):
    with pytest.raises(ValidationError):
        process_image(upload(fake_jpg_text))
