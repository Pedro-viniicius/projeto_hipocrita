"""Texto da mensagem enviada ao vendedor pelo WhatsApp.

Modelo da spec (`oferta.mensagem_whatsapp`). Os marcadores entre chaves são
preenchidos por `apps/catalog/domain/whatsapp.py`.
"""

MESSAGE = "Oi! Vi “{title}” no Pão de Cada Dia. Ainda está disponível?"
MESSAGE_WITH_VARIANT = (
    "Oi! Vi “{title}”, opção “{variant}” no Pão de Cada Dia. Ainda está disponível?"
)
# Endereço da oferta numa linha à parte, para o vendedor achar o anúncio.
MESSAGE_LINK_LINE = "{url}"
