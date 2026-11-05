"""Validação e processamento de fotos (Pillow).

- O tipo vem do **conteúdo**: o Pillow decodifica o arquivo e só aceita JPEG, PNG
  e WebP (`img.format`). Extensão e `content_type` enviados são ignorados.
- O limite de pixels (24 MP) é conferido pelo cabeçalho, antes de decodificar,
  e barra "bombas de descompressão".
- Memória: o JPEG é decodificado já reduzido (`draft`, escala DCT) até o menor
  tamanho que ainda tem 1280 px nos dois lados; a imagem da página é reduzida
  no lugar (`thumbnail` com `reducing_gap`) e a rotação EXIF não faz cópia
  quando não há o que girar.
- A saída é regravada em WebP (qualidade 80) a partir dos pixels, já com a
  rotação EXIF aplicada e sem nenhum metadado (EXIF, GPS, XMP, ICC).
"""

import io
import struct
import warnings
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

from texts import photos as texts

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
MAX_PIXELS = 24_000_000
CARD_SIZE = (480, 480)
PAGE_MAX_SIDE = 1280
WEBP_QUALITY = 80
# Reduz primeiro por um fator inteiro (rápido, pouca memória) e só termina com
# LANCZOS; 3.0 fica visualmente igual ao LANCZOS puro (documentação do Pillow).
REDUCING_GAP = 3.0
# Tamanho mínimo pedido ao decodificador do JPEG: garante lado maior >= 1280 para
# a página e lado menor >= 480 para o card, sem decodificar a foto inteira.
JPEG_DRAFT_SIZE = (PAGE_MAX_SIDE, PAGE_MAX_SIDE)

# Erros que o Pillow pode levantar com arquivo corrompido ou malicioso.
_DECODE_ERRORS = (
    UnidentifiedImageError,
    Image.DecompressionBombError,
    Image.DecompressionBombWarning,
    OSError,
    SyntaxError,
    ValueError,
    EOFError,
    IndexError,
    TypeError,
    struct.error,
)


@dataclass(frozen=True)
class Processed:
    card: ContentFile  # 480×480, corte central, WebP q80, sem EXIF
    page: ContentFile  # lado maior até 1280, WebP q80, sem EXIF
    width: int  # largura da imagem da página
    height: int  # altura da imagem da página


def _max_bytes() -> int:
    return settings.MAX_UPLOAD_MB * 1024 * 1024


def _invalid() -> ValidationError:
    return ValidationError(texts.PHOTO_INVALID, code="invalid_image")


def _open(f: UploadedFile) -> Image.Image:
    """Abre do início do arquivo; avisos de bomba de descompressão viram erro."""
    f.seek(0)
    return Image.open(f, formats=sorted(ALLOWED_FORMATS))


def validate_image(f: UploadedFile) -> None:
    """Levanta `ValidationError` se o arquivo não for JPEG/PNG/WEBP real, passar de
    `MAX_UPLOAD_MB` ou de 24 MP."""
    size = getattr(f, "size", None)
    if size is None or size > _max_bytes():
        raise ValidationError(
            texts.PHOTO_TOO_LARGE.format(mb=settings.MAX_UPLOAD_MB), code="too_large"
        )
    if size == 0:
        raise _invalid()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with _open(f) as img:
                if img.format not in ALLOWED_FORMATS:
                    raise _invalid()
                width, height = img.size
                if width < 1 or height < 1:
                    raise _invalid()
                if width * height > MAX_PIXELS:
                    raise ValidationError(texts.PHOTO_TOO_MANY_PIXELS, code="too_many_pixels")
                img.verify()
        except ValidationError:
            raise
        except _DECODE_ERRORS:
            raise _invalid() from None
        finally:
            f.seek(0)


def _clean_mode(img: Image.Image) -> Image.Image:
    """RGB, ou RGBA quando a imagem tem transparência (o WebP guarda alfa)."""
    has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    target = "RGBA" if has_alpha else "RGB"
    return img if img.mode == target else img.convert(target)


def _to_webp(img: Image.Image, name: str) -> ContentFile:
    img.info = {}  # nada de metadado herdado (o WebP só grava o que for passado)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
    return ContentFile(buf.getvalue(), name=name)


def process_image(f: UploadedFile) -> Processed:
    """Corrige a rotação EXIF, remove metadados e gera os dois tamanhos em WebP.

    Chame `validate_image` antes: aqui os erros de decodificação também viram
    `ValidationError`, mas sem a checagem de tamanho do arquivo.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            # Tudo dentro do `with`: a imagem é girada e reduzida no lugar e o
            # `close()` libera a memória dela no fim.
            with _open(f) as src:
                if src.format not in ALLOWED_FORMATS:
                    raise _invalid()
                if src.size[0] * src.size[1] > MAX_PIXELS:
                    raise ValidationError(texts.PHOTO_TOO_MANY_PIXELS, code="too_many_pixels")
                if src.format == "JPEG":
                    src.draft("RGB", JPEG_DRAFT_SIZE)  # antes do load(): decodifica reduzido
                src.load()
                ImageOps.exif_transpose(src, in_place=True)
                base = _clean_mode(src)
                card = ImageOps.fit(
                    base, CARD_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
                )
                base.thumbnail(
                    (PAGE_MAX_SIDE, PAGE_MAX_SIDE),
                    Image.Resampling.LANCZOS,
                    reducing_gap=REDUCING_GAP,
                )
                width, height = base.size
                return Processed(
                    card=_to_webp(card, "card.webp"),
                    page=_to_webp(base, "page.webp"),
                    width=width,
                    height=height,
                )
        except ValidationError:
            raise
        except _DECODE_ERRORS:
            raise _invalid() from None
        finally:
            f.seek(0)
