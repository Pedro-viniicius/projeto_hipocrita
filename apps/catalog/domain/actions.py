"""Ações do vendedor sobre um anúncio (CA7, CA9, CA10). Só mudam atributos; o serviço grava."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from .availability import daily_expires_at, is_available_today, needs_reconfirmation

ACTIONS = {
    "pause",
    "resume",
    "sold_out",
    "restock",
    "sold",
    "unsold",
    "confirm_today",
    "reconfirm",
}
# Ordem em que o painel mostra os botões.
_ORDER = (
    "confirm_today",
    "reconfirm",
    "sold_out",
    "restock",
    "sold",
    "unsold",
    "pause",
    "resume",
)
_CONFIRMABLE_KINDS = {"recurring", "daily"}


class ActionNotAllowed(Exception):
    """A ação não vale para o estado atual. `reason` é um código estável para a view."""

    def __init__(self, action: str, reason: str) -> None:
        super().__init__(f"{action}: {reason}")
        self.action = action
        self.reason = reason


def _refusal(offer, action: str) -> str | None:
    """Motivo (código) de a ação não valer para este anúncio, ou `None` se vale."""
    if action not in ACTIONS:
        return "unknown_action"
    if offer.hidden_at is not None:
        return "hidden"
    status, kind = offer.status, offer.kind
    one_off = kind == "one_off"
    rules = {
        "pause": status in {"active", "sold_out"},
        "resume": status == "paused",
        "sold_out": status == "active" and not one_off,
        "restock": status == "sold_out",
        "sold": status == "active" and one_off,
        "unsold": status == "sold" and one_off,
        "confirm_today": kind in _CONFIRMABLE_KINDS and status != "sold",
        "reconfirm": status == "active" and one_off,
    }
    return None if rules[action] else "wrong_state"


def confirmation_refusal(closing_time: time | None, now: datetime, tz: ZoneInfo) -> str | None:
    """Motivo de não dar para confirmar "disponível hoje" agora, ou `None` se dá.

    `closing_time` é o horário de encerramento que vai valer (`None`: até 23:59).
    - "closing_passed": o encerramento de hoje já passou (CA9);
    - "day_over": já chegou 23:59, quando toda confirmação do dia acaba; confirmar
      agora não teria efeito nenhum.
    Usada pelo botão (`apply_action`) e pelo formulário do anúncio.
    """
    local = now.astimezone(tz)
    if closing_time is not None and closing_time.replace(tzinfo=None) <= local.time():
        return "closing_passed"
    if local >= daily_expires_at(local.date(), closing_time, tz):
        return "day_over"
    return None


def allowed_actions(offer, now: datetime, tz: ZoneInfo, days: int) -> list[str]:
    """Ações oferecidas ao vendedor agora, na ordem de exibição."""
    result = []
    for action in _ORDER:
        if _refusal(offer, action) is not None:
            continue
        if action == "confirm_today":
            closing = offer.closing_time if offer.kind == "daily" else None
            if offer.status == "active" and is_available_today(
                offer.daily_confirmed_on, closing, now, tz
            ):
                continue  # já está confirmada
        if action == "reconfirm" and not needs_reconfirmation(offer.last_confirmed_at, now, days):
            continue
        result.append(action)
    return result


def apply_action(
    offer,
    action: str,
    now: datetime,
    tz: ZoneInfo,
    closing_time: time | None = None,
) -> None:
    """Aplica a ação no objeto (sem salvar). Levanta `ActionNotAllowed` se não vale.

    `confirm_today` só vale para recorrente e do dia e recusa horário de
    encerramento que já passou hoje (CA9) e confirmação a partir de 23:59
    (`confirmation_refusal`). Na oferta do dia, `closing_time`
    novo substitui o salvo no anúncio; na recorrente o horário é ignorado.
    Reconfirmar, reativar e "voltar a vender" de venda pontual renovam
    `last_confirmed_at` (CA10, D10).
    """
    reason = _refusal(offer, action)
    if reason is not None:
        raise ActionNotAllowed(action, reason)
    local = now.astimezone(tz)

    if action == "confirm_today":
        effective = None
        if offer.kind == "daily":
            effective = closing_time if closing_time is not None else offer.closing_time
        refusal = confirmation_refusal(effective, now, tz)
        if refusal is not None:
            raise ActionNotAllowed(action, refusal)
        if offer.kind == "daily":
            offer.closing_time = effective
        offer.daily_confirmed_on = local.date()
        offer.status = "active"
        offer.status_changed_at = now
        return

    new_status = {
        "pause": "paused",
        "resume": "active",
        "sold_out": "sold_out",
        "restock": "active",
        "sold": "sold",
        "unsold": "active",
        "reconfirm": "active",
    }[action]
    if offer.status != new_status:
        offer.status = new_status
        offer.status_changed_at = now
    if offer.kind == "one_off" and action in {"reconfirm", "resume", "unsold"}:
        offer.last_confirmed_at = now
