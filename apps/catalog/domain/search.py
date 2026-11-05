"""Busca sem acento nem diferença de maiúsculas (D13). Pura: o ORM não entra aqui."""

import re
import unicodedata

MAX_QUERY_LENGTH = 80
MAX_TERMS = 6
MIN_TERM_LENGTH = 2


def strip_control(text: str) -> str:
    """Troca caracteres de controle (NUL, tabulação, quebra de linha…) por espaço e
    colapsa os espaços. O PostgreSQL recusa NUL em texto, e nenhum deles serve à busca."""
    return " ".join(
        "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text or "").split()
    )


def normalize(text: str) -> str:
    """`casefold`, sem acento (NFKD), sem caracteres de controle e com espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", strip_control(text))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", plain.casefold()).strip()


def split_terms(q: str) -> list[str]:
    """Até 6 termos normalizados de 2+ caracteres, sem repetição; `q` é cortado em 80."""
    terms: list[str] = []
    for term in normalize((q or "")[:MAX_QUERY_LENGTH]).split(" "):
        if len(term) >= MIN_TERM_LENGTH and term not in terms:
            terms.append(term)
    return terms[:MAX_TERMS]


def match_tier(terms: list[str], title: str, seller_name: str, body: str) -> int | None:
    """Prioridade da oferta para a busca; todos os termos precisam casar.

    0: tudo no título; 1: título e nome do vendedor; 2: com descrição, variações
    e categoria (`body`). `None`: não casa. Sem termos, todo anúncio é 0.
    """
    if not terms:
        return 0
    haystack = normalize(title)
    if all(t in haystack for t in terms):
        return 0
    haystack = f"{haystack} {normalize(seller_name)}"
    if all(t in haystack for t in terms):
        return 1
    haystack = f"{haystack} {normalize(body)}"
    if all(t in haystack for t in terms):
        return 2
    return None
