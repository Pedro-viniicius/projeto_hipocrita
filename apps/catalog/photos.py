"""Gravação das fotos de um anúncio (CA11, CA13).

- Só remove fotos do próprio anúncio: o filtro `offer=offer` vale mesmo que a
  lista de ids venha adulterada.
- O anúncio fica travado (`select_for_update`) enquanto as fotos mudam, para
  dois envios ao mesmo tempo não passarem de 3 fotos.
- Os arquivos são regravados pelo `imaging.process_image` (WebP, sem EXIF) e
  salvos pelo `default_storage` com nome UUID (`models.offer_*_path`). Se algo
  falhar no meio, os arquivos já gravados nesta chamada são apagados.
"""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from apps.catalog.imaging import process_image, validate_image
from apps.catalog.models import Offer, OfferPhoto
from texts import seller as texts

logger = logging.getLogger(__name__)


def too_many_photos_error() -> ValidationError:
    return ValidationError(
        texts.PHOTOS_TOO_MANY.format(max=settings.MAX_PHOTOS_PER_OFFER), code="too_many_photos"
    )


def _discard(names: list[str]) -> None:
    """Apaga arquivos gravados por uma chamada que não chegou ao fim."""
    for name in names:
        try:
            OfferPhoto._meta.get_field("card_image").storage.delete(name)
        except Exception:
            # Sem o nome do arquivo no log: basta saber que algo ficou para trás.
            logger.warning("Não foi possível apagar um arquivo de foto não usado.")


def _compact_positions(photos: list[OfferPhoto]) -> None:
    """Renumera as fotos que ficaram para 0, 1, 2… mantendo a ordem.

    Em ordem crescente, cada foto só desce para uma posição já liberada, então a
    restrição única (offer, position) nunca é violada no meio do caminho.
    """
    for index, photo in enumerate(photos):
        if photo.position != index:
            photo.position = index
            photo.save(update_fields=["position"])


def save_offer_photos(offer: Offer, files: list[UploadedFile], remove_ids: list[int]) -> None:
    """Remove as fotos `remove_ids` **deste** anúncio e grava as novas (até 3 no total).

    Levanta `ValidationError` se o total passar do limite ou se um arquivo não
    for uma foto válida; nesse caso a transação é desfeita e nada fica gravado.
    """
    written: list[str] = []
    try:
        with transaction.atomic():
            Offer.objects.select_for_update().only("pk").get(pk=offer.pk)
            if remove_ids:
                # A remoção dos arquivos acontece no `post_delete` (signals.py), após o commit.
                for photo in OfferPhoto.objects.filter(offer=offer, pk__in=remove_ids):
                    photo.delete()
            remaining = list(OfferPhoto.objects.filter(offer=offer).order_by("position", "pk"))
            if len(remaining) + len(files) > settings.MAX_PHOTOS_PER_OFFER:
                raise too_many_photos_error()
            _compact_positions(remaining)
            for position, upload in enumerate(files, start=len(remaining)):
                validate_image(upload)
                processed = process_image(upload)
                photo = OfferPhoto(
                    offer=offer,
                    position=position,
                    page_width=processed.width,
                    page_height=processed.height,
                )
                photo.card_image.save(processed.card.name, processed.card, save=False)
                written.append(photo.card_image.name)
                photo.page_image.save(processed.page.name, processed.page, save=False)
                written.append(photo.page_image.name)
                photo.save()
    except BaseException:
        _discard(written)
        raise
