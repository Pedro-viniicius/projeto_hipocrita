"""Textos de interface da área do vendedor: painel, formulário de anúncio e perfil.

Nascem no Python (rótulos, dicas e erros de formulário, mensagens de feedback,
rótulos das ações). O designer pode mudar o texto; os nomes das constantes não
mudam. Os erros de validação da foto (tamanho, tipo) vêm de `texts/photos.py`.
"""

# Comuns -----------------------------------------------------------------------
REQUIRED = "Preencha este campo."
CHOICE_INVALID = "Escolha uma das opções."

# Painel "Meus anúncios" -------------------------------------------------------
KIND_LABELS = {
    "recurring": "Sempre na vitrine",
    "daily": "Oferta do dia",
    "one_off": "Venda única",
}
# `{hora}`: "23h59" ou o horário de encerramento ("18:00").
CONFIRMED_UNTIL = "Confirmado até {hora}"
CONFIRMED_UNTIL_END_OF_DAY = "23h59"
LAST_CONFIRMATION_TODAY = "Última confirmação hoje"
LAST_CONFIRMATION_ONE_DAY = "Última confirmação há 1 dia"
LAST_CONFIRMATION_DAYS = "Última confirmação há {n} dias"
PRICE_FROM = "A partir de"

PENDING_NOTICE = (
    "Seu primeiro anúncio está em análise. Quando for aprovado, ele aparece para todo mundo."
)
# Antes e depois do link para o Perfil (D4: sem WhatsApp liberado, nada fica público).
CONTACT_NOTICE_BEFORE = (
    "Seu WhatsApp não está liberado, então seus anúncios não aparecem na vitrine. "
)
CONTACT_NOTICE_LINK = "Libere o contato no Perfil"
CONTACT_NOTICE_AFTER = "."

# Rótulo do botão de cada ação (`domain.actions.ACTIONS`).
ACTION_LABELS = {
    "confirm_today": "Confirmar disponível hoje",
    "reconfirm": "Confirmar que ainda vendo",
    "pause": "Pausar",
    "resume": "Reativar",
    "sold_out": "Marcar como esgotado",
    "restock": "Voltou ao estoque",
    "sold": "Marcar como vendido",
    "unsold": "Voltar a vender",
}
# Mensagem depois de cada ação. `{titulo}` é o título do anúncio.
ACTION_DONE = {
    "confirm_today": "Pronto: “{titulo}” confirmado como disponível hoje.",
    "reconfirm": "Pronto: “{titulo}” confirmado. Ele continua na vitrine.",
    "pause": "“{titulo}” pausado. Ele saiu da vitrine.",
    "resume": "“{titulo}” reativado.",
    "sold_out": "“{titulo}” marcado como esgotado.",
    "restock": "“{titulo}” voltou ao estoque.",
    "sold": "“{titulo}” marcado como vendido.",
    "unsold": "“{titulo}” voltou a ficar à venda.",
}
# Erro no formulário quando o anúncio mudou entre a validação e a gravação.
ACTION_FAILED = "Não conseguimos salvar. Tente de novo."
ACTION_NOT_ALLOWED = "Essa ação não vale para este anúncio agora. Confira o estado dele na lista."
ACTION_CLOSING_PASSED = (
    "O horário de encerramento de hoje já passou. Edite o anúncio para mudar o horário."
)
ACTION_DAY_OVER = (
    "A confirmação de hoje vale só até 23h59, e esse horário já chegou. Confirme de novo amanhã."
)

# Formulário de anúncio --------------------------------------------------------
# `{dias}` em `KIND_HELP` é o prazo de reconfirmação (`settings.RECONFIRM_DAYS`).
KIND_LABEL = "O que você vai anunciar?"
KIND_CHOICES = {
    "recurring": "Faço sempre (ou por encomenda)",
    "daily": "Tenho hoje",
    "one_off": "Venda única",
}
KIND_HELP = {
    "recurring": "Fica na vitrine até você pausar.",
    "daily": "Só aparece em “Disponíveis hoje” depois que você confirma. Vale até 23h59 do dia.",
    "one_off": "Fica até você marcar como vendido. Pedimos para você confirmar a cada {dias} dias.",
}
TITLE_LABEL = "Título"
TITLE_HELP = "Exemplo: Bolo de pote de ninho com morango"
CATEGORY_LABEL = "Categoria"
CATEGORY_EMPTY = "Escolha uma categoria"
PRICE_LABEL = "Preço (ou o menor preço), em R$"
PRICE_HELP = "Exemplo: 8,50"
DESCRIPTION_LABEL = "Descrição curta"
DESCRIPTION_HELP = "Exemplo: Feito no dia. Dá pra pedir sem leite."
FULFILLMENT_LABEL = "Retirada ou entrega"
FULFILLMENT_HELP = "Exemplo: Retirada no bloco 3, no intervalo das 10h"

VARIANTS_LEGEND = "Opções com preços diferentes"
VARIANTS_HELP = "Deixe em branco o que não usar."
# `{n}` é o número da linha (1 a 5): o rótulo precisa ser único na página.
VARIANT_NAME_LABEL = "Nome da opção {n}"
VARIANT_NAME_HELP = "Exemplo: Ninho com morango"
VARIANT_PRICE_LABEL = "Preço da opção {n}"
VARIANT_PRICE_HELP = "Exemplo: 8,00"

PHOTOS_LABEL = "Fotos"
PHOTOS_HELP = (
    "Até 3 fotos, cada uma de até {mb} MB (JPG, PNG ou WebP). "
    "Se o formulário voltar com erro, escolha as fotos de novo."
)
PHOTOS_CURRENT = "Fotos atuais"
PHOTO_REMOVE = "Remover esta foto"

DAILY_LEGEND = "Só para oferta do dia"
DAILY_INSTRUCTION = "Preencha só se você escolheu “Tenho hoje”."
CLOSING_LABEL = "Horário de encerramento"
CLOSING_HELP = "Se deixar em branco, vale até 23h59."
CONFIRM_TODAY_LABEL = "Já confirmar como disponível hoje"

FOOD_LEGEND = "Só para comidas e bebidas"
FOOD_INSTRUCTION = "Preencha só se a categoria for de comida ou bebida."
FOOD_HELP = (
    "Se você não preencher, a página mostra “Não informado pelo vendedor”. "
    "Escreva só o que você tem certeza."
)
PORTION_LABEL = "Porção"
PORTION_HELP = "Exemplo: 1 pote de 200 g"
INGREDIENTS_LABEL = "Ingredientes"
INGREDIENTS_HELP = "Exemplo: Leite, ninho, morango, açúcar."
ALLERGENS_LABEL = "Alergênicos"
ALLERGENS_HELP = "Exemplo: Contém leite. Pode conter traços de amendoim."

# Erros do formulário de anúncio.
PRICE_INVALID = "Digite um valor em reais. Exemplo: 8,50"
PRICE_TOO_HIGH = "O valor máximo é R$ 100.000,00."
TIME_INVALID = "Digite um horário válido. Exemplo: 18:00"
CLOSING_PASSED = (
    "Esse horário de hoje já passou. "
    "Mude o horário ou desmarque “Já confirmar como disponível hoje”."
)
CONFIRM_DAY_OVER = (
    "A confirmação de hoje vale só até 23h59, e esse horário já chegou. "
    "Desmarque “Já confirmar como disponível hoje” e confirme amanhã."
)
VARIANT_NAME_MISSING = "Dê um nome para esta opção ou apague o preço."
VARIANT_PRICE_MISSING = "Digite o preço desta opção. Exemplo: 8,00"
VARIANT_NAME_REPEATED = "Já existe uma opção com este nome."
PHOTOS_TOO_MANY = "Você pode ter até {max} fotos. Remova alguma ou envie menos."
PHOTOS_RATE_LIMITED = (
    "Você enviou muitas fotos em pouco tempo. Espere um pouco ou salve sem fotos novas."
)
PHOTO_REMOVE_INVALID = "Escolha só fotos deste anúncio."

# Títulos, botões e mensagens do formulário de anúncio.
OFFER_NEW_TITLE = "Novo anúncio"
OFFER_EDIT_TITLE = "Editar anúncio"
OFFER_CREATED_PENDING = (
    "Anúncio enviado para análise. Ele aparece para todo mundo quando a equipe aprovar."
)
OFFER_CREATED = "Anúncio publicado. Já está na vitrine."
OFFER_CREATED_NO_CONTACT = (
    "Anúncio salvo. Ele só aparece na vitrine depois que você liberar o WhatsApp no Perfil."
)
OFFER_SAVED = "Alterações salvas."
# Teto de anúncios por vendedor. `{max}` é o limite.
OFFER_LIMIT_REACHED = (
    "Você já tem {max} anúncios, o máximo permitido. "
    "Para anunciar outra coisa, edite um anúncio que você não usa mais."
)
PENDING_LIMIT_REACHED = (
    "Você já tem {max} anúncios aguardando aprovação. "
    "Espere a equipe analisar esses antes de criar outro."
)

# Perfil -----------------------------------------------------------------------
NAME_LABEL = "Nome ou marca"
NAME_HELP = "Exemplo: Doces da Ana. Se você mudar o nome, o link da sua página também muda."
NAME_INVALID = "Digite um nome com pelo menos uma letra ou número."
BIO_LABEL = "Apresentação"
BIO_HELP = "Exemplo: Cookies e brownies feitos em casa. Sábado entrego no campus."
AREA_LABEL = "Onde você atende"
AREA_HELP = "Exemplo: Campus Paraíso, blocos 1 a 3"
HOURS_LABEL = "Horários"
HOURS_HELP = "Exemplo: Seg a sex, no intervalo das 10h"
WHATSAPP_LABEL = "WhatsApp com DDD"
WHATSAPP_HELP = "Exemplo: (35) 91234-5678"
WHATSAPP_INVALID = "Digite um WhatsApp válido com DDD. Exemplo: (35) 91234-5678"
WHATSAPP_PUBLIC_LABEL = "Mostrar o número para quem quer comprar?"
WHATSAPP_PUBLIC_HELP = (
    "Você pode mudar isso quando quiser. Se mudar para “Não”, o contato some na hora."
)
WHATSAPP_PUBLIC_YES = "Sim, mostrar. O botão “Consultar no WhatsApp” fica ativo nos meus anúncios."
WHATSAPP_PUBLIC_NO = "Não. Meus anúncios ficam sem botão de contato e saem da vitrine."

PROFILE_SAVED = "Perfil atualizado."
PROFILE_CONTACT_REVOKED = (
    "Perfil atualizado. Seu número não aparece mais e seus anúncios saíram da vitrine."
)
PROFILE_CONTACT_GRANTED = (
    "Perfil atualizado. O botão “Consultar no WhatsApp” já aparece nos seus anúncios aprovados."
)
# Somado à mensagem acima quando o nome muda: o link público é gerado do nome.
PROFILE_LINK_CHANGED = (
    "Como o nome mudou, o link da sua página também mudou. Compartilhe o link novo."
)
