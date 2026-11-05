"""Remove os arquivos de uma foto depois que a linha some do banco.

Vale para remoção direta e para cascata (anúncio apagado, conta excluída). Os
arquivos só são apagados depois do commit: se a transação desfizer, nada se perde.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.catalog.models import OfferPhoto

logger = logging.getLogger(__name__)


def _delete_files(storage, names: list[str]) -> None:
    for name in names:
        try:
            storage.delete(name)
        except Exception:
            # Sem o nome do arquivo no log: basta saber que algo ficou para trás.
            logger.warning("Não foi possível apagar um arquivo de foto removida.")


@receiver(post_delete, sender=OfferPhoto, dispatch_uid="catalog_delete_photo_files")
def delete_photo_files(sender, instance: OfferPhoto, **kwargs) -> None:
    files = [instance.card_image, instance.page_image]
    names = [f.name for f in files if f and f.name]
    if not names:
        return
    storage = instance.card_image.storage
    transaction.on_commit(lambda: _delete_files(storage, names))
