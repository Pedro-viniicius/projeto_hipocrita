"""Modelos de visão da vitrine pública.

`OfferCardVM` é o contrato do componente `templates/components/offer_card.html`
(plano, "Esquema e contratos"): o designer usa só esses campos. `ListParams`
guarda o contexto da lista (`q`, `cat`, `hoje`, `pagina`) que os links do
cartão e o "Voltar" da oferta carregam (CA2).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.http import QueryDict
from django.urls import reverse

from apps.catalog.domain.pricing import display_price, format_brl
from apps.catalog.domain.search import MAX_QUERY_LENGTH, strip_control
from apps.catalog.domain.states import PublicState, StateVM, public_state, state_vm
from apps.catalog.models import Offer

PAGE_SIZE = 20  # cartões por página, cumulativo (D25)
MAX_PAGE = 50  # teto de `pagina` (1.000 cartões), para não aceitar valores absurdos
EAGER_CARDS = 2  # as 2 primeiras fotos da lista carregam já (spec 2.5)
CARD_PHOTO_SIZE = 480  # o card_image é 480×480 (imaging.py)
_SLUG_RE = re.compile(r"^[-a-zA-Z0-9_]{1,50}$")
_STOPWORDS = {"da", "de", "do", "das", "dos", "e"}


@dataclass(frozen=True)
class OfferCardVM:
    anchor_id: str
    url: str
    title: str
    photo_url: str | None
    photo_w: int
    photo_h: int
    price_label: str
    price_from: bool
    price_struck: bool
    state: StateVM | None
    seller_name: str
    fulfillment: str
    eager: bool


@dataclass(frozen=True)
class ListParams:
    """Contexto da lista, já saneado. Só estes 4 parâmetros viajam nos links."""

    q: str = ""
    cat: str = ""
    hoje: bool = False
    pagina: int = 1

    @classmethod
    def from_query(cls, query: QueryDict, valid_categories: set[str] | None = None) -> ListParams:
        """Lê da query string. Valor inválido vira o padrão (nunca erro).

        `valid_categories`: slugs aceitos em `cat`; `None` aceita qualquer slug
        bem formado (a página da oferta só repassa para o "Voltar").
        """
        # Sem caracteres de controle: NUL quebraria a gravação no PostgreSQL (Q1).
        q = strip_control((query.get("q") or "")[:MAX_QUERY_LENGTH])
        cat = (query.get("cat") or "").strip()
        if not _SLUG_RE.match(cat) or (
            valid_categories is not None and cat not in valid_categories
        ):
            cat = ""
        try:
            pagina = int(query.get("pagina") or 1)
        except ValueError:
            pagina = 1
        return cls(
            q=q, cat=cat, hoje=query.get("hoje") == "1", pagina=min(max(pagina, 1), MAX_PAGE)
        )

    @property
    def has_filters(self) -> bool:
        return bool(self.q or self.cat or self.hoje)

    def query_string(self, **changes) -> str:
        """Query string com os parâmetros não vazios (`pagina` só acima de 1)."""
        values = {"q": self.q, "cat": self.cat, "hoje": self.hoje, "pagina": self.pagina}
        values.update(changes)
        pairs = []
        if values["q"]:
            pairs.append(("q", values["q"]))
        if values["cat"]:
            pairs.append(("cat", values["cat"]))
        if values["hoje"]:
            pairs.append(("hoje", "1"))
        if values["pagina"] and values["pagina"] > 1:
            pairs.append(("pagina", str(values["pagina"])))
        return urlencode(pairs)

    def home_url(self, anchor: str = "", **changes) -> str:
        qs = self.query_string(**changes)
        url = reverse("catalog:home") + (f"?{qs}" if qs else "")
        return f"{url}#{anchor}" if anchor else url


def anchor_id(offer_id: int) -> str:
    return f"oferta-{offer_id}"


def offer_url(offer_id: int, params: ListParams | None = None) -> str:
    """Link da oferta levando o contexto da lista (CA2)."""
    url = reverse("catalog:offer_detail", kwargs={"pk": offer_id})
    qs = params.query_string() if params is not None else ""
    return f"{url}?{qs}" if qs else url


def price_info(offer: Offer) -> tuple[str, bool]:
    """(preço formatado, é "A partir de"), contando as variações (`display_price`)."""
    cents, from_ = display_price(offer.price_cents, [v.price_cents for v in offer.variants.all()])
    return format_brl(cents), from_


def offer_state(offer: Offer, now: datetime, tz: ZoneInfo) -> tuple[PublicState, StateVM | None]:
    state = public_state(offer, now, tz)
    return state, state_vm(state)


def build_card(
    offer: Offer,
    *,
    now: datetime,
    tz: ZoneInfo,
    params: ListParams | None = None,
    eager: bool = False,
) -> OfferCardVM:
    state, vm = offer_state(offer, now, tz)
    price_label, price_from = price_info(offer)
    photos = list(offer.photos.all())
    return OfferCardVM(
        anchor_id=anchor_id(offer.pk),
        url=offer_url(offer.pk, params),
        title=offer.title,
        photo_url=photos[0].card_image.url if photos else None,
        photo_w=CARD_PHOTO_SIZE,
        photo_h=CARD_PHOTO_SIZE,
        price_label=price_label,
        price_from=price_from,
        price_struck=state == PublicState.SOLD,
        state=vm,
        seller_name=offer.seller.display_name,
        fulfillment=offer.fulfillment,
        eager=eager,
    )


def build_cards(
    offers: list[Offer], *, now: datetime, tz: ZoneInfo, params: ListParams | None = None
) -> list[OfferCardVM]:
    return [
        build_card(o, now=now, tz=tz, params=params, eager=i < EAGER_CARDS)
        for i, o in enumerate(offers)
    ]


def initials(name: str) -> str:
    """Até duas iniciais do nome, sem conectivos ("Doces da Ana" → "DA")."""
    words = [w for w in re.findall(r"\w+", name or "") if w.casefold() not in _STOPWORDS]
    return "".join(w[0] for w in words[:2]).upper()
