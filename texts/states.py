"""Rótulos e ícones dos estados de um anúncio (selos).

O designer pode mudar o texto; os nomes das constantes não mudam. Os ícones
são ids do sprite `static/icones.svg` (sem o prefixo `i-`).
"""

# Estados públicos (visitante e vendedor).
LABEL_AVAILABLE_TODAY = "Disponível hoje"
LABEL_ON_ORDER = "Sob encomenda"
LABEL_SOLD_OUT = "Esgotado"
LABEL_SOLD = "Vendido"

# Estados só do vendedor e da administração.
LABEL_PAUSED = "Pausado"
LABEL_NEEDS_CONFIRMATION = "Precisa de confirmação"
LABEL_PENDING_APPROVAL = "Aguardando aprovação"
LABEL_HIDDEN = "Oculto pela administração"

ICON_AVAILABLE_TODAY = "circulo-check"
ICON_ON_ORDER = "relogio"
ICON_SOLD_OUT = "circulo-menos"
ICON_SOLD = "etiqueta-check"
ICON_PAUSED = "pausa"
ICON_NEEDS_CONFIRMATION = "alerta-circulo"
ICON_PENDING_APPROVAL = "ampulheta"
ICON_HIDDEN = "circulo-menos"

# Chave do estado (valor do enum em `domain/states.py`) -> (rótulo, ícone).
STATES = {
    "available_today": (LABEL_AVAILABLE_TODAY, ICON_AVAILABLE_TODAY),
    "on_order": (LABEL_ON_ORDER, ICON_ON_ORDER),
    "sold_out": (LABEL_SOLD_OUT, ICON_SOLD_OUT),
    "sold": (LABEL_SOLD, ICON_SOLD),
    "paused": (LABEL_PAUSED, ICON_PAUSED),
    "needs_confirmation": (LABEL_NEEDS_CONFIRMATION, ICON_NEEDS_CONFIRMATION),
    "pending_approval": (LABEL_PENDING_APPROVAL, ICON_PENDING_APPROVAL),
    "hidden": (LABEL_HIDDEN, ICON_HIDDEN),
}
