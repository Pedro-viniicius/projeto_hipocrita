"""Textos de interface das fotos (validação do upload e limite do envio).

O designer pode mudar o texto; os nomes das constantes não mudam.
"""

# `{mb}` é o limite por foto (`settings.MAX_UPLOAD_MB`).
PHOTO_TOO_LARGE = "Esta foto passou de {mb} MB. Escolha uma menor."
PHOTO_INVALID = "Este arquivo não é uma foto válida. Use JPG, PNG ou WebP."
PHOTO_TOO_MANY_PIXELS = "Esta foto tem resolução grande demais. Escolha uma menor."

# Resposta 413 (corpo da requisição acima do limite total).
REQUEST_TOO_LARGE_TITLE = "Envio grande demais"
REQUEST_TOO_LARGE_TEXT = (
    "As fotos enviadas passaram do limite. Envie até 3 fotos de até {mb} MB cada e tente de novo."
)
REQUEST_TOO_LARGE_BACK = "Voltar para o início"
