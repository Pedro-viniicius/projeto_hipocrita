"""Celular brasileiro para o WhatsApp do vendedor.

O formato guardado é `55DD9XXXXXXXX` (13 dígitos). O número é dado pessoal:
nunca registrar em log nem em mensagem de erro.
"""

import re

# Os 67 DDDs em uso no Brasil (Anatel).
VALID_DDDS = frozenset(
    {
        11, 12, 13, 14, 15, 16, 17, 18, 19,
        21, 22, 24, 27, 28,
        31, 32, 33, 34, 35, 37, 38,
        41, 42, 43, 44, 45, 46, 47, 48, 49,
        51, 53, 54, 55,
        61, 62, 63, 64, 65, 66, 67, 68, 69,
        71, 73, 74, 75, 77, 79,
        81, 82, 83, 84, 85, 86, 87, 88, 89,
        91, 92, 93, 94, 95, 96, 97, 98, 99,
    }
)  # fmt: skip

COUNTRY_CODE = "55"
# Entrada maior que isto não é um telefone (evita trabalho com texto colado).
MAX_RAW_LENGTH = 40
_NON_DIGIT = re.compile(r"\D")


def normalize_br_mobile(raw: str) -> str | None:
    """Devolve `55DD9XXXXXXXX` ou `None` se não for um celular brasileiro válido.

    Aceita formatos comuns: "(35) 91234-5678", "35 9 1234 5678",
    "+55 35 91234-5678", "035912345678". Telefone fixo é recusado (D5).
    """
    if not raw or len(raw) > MAX_RAW_LENGTH:
        return None
    digits = _NON_DIGIT.sub("", raw)
    # "0" de tronco (035...) ou de discagem internacional (0055...).
    digits = digits.lstrip("0")
    if len(digits) in (12, 13) and digits.startswith(COUNTRY_CODE):
        digits = digits[len(COUNTRY_CODE) :]
    if len(digits) != 11:
        return None
    ddd, local = int(digits[:2]), digits[2:]
    if ddd not in VALID_DDDS or not local.startswith("9"):
        return None
    return COUNTRY_CODE + digits


def format_br_mobile(number: str) -> str:
    """`"5535912345678"` → `"(35) 91234-5678"`. Entrada fora do formato volta igual."""
    digits = _NON_DIGIT.sub("", number or "")
    if len(digits) == 13 and digits.startswith(COUNTRY_CODE):
        digits = digits[len(COUNTRY_CODE) :]
    if len(digits) != 11:
        return number
    return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
