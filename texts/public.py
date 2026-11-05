"""Textos de interface da vitrine pública: lista, oferta, vendedor e denúncia.

Só os textos que nascem no Python (títulos montados com o termo da busca,
estados vazios, rótulos e erros do formulário de denúncia). O texto fixo de
página fica no template. O designer pode mudar o texto; os nomes das
constantes não mudam. A mensagem do WhatsApp fica em `texts/whatsapp.py`.
"""

# Página inicial ----------------------------------------------------------------
HOME_PAGE_TITLE = "Ofertas no campus"
HOME_HEADING = "O que tem no campus hoje?"
CATEGORY_ALL = "Tudo"

# `h2` da lista (sem contadores).
LIST_TITLE = "Ofertas"
LIST_TITLE_TODAY = "Disponíveis hoje"
LIST_TITLE_SEARCH = "Resultados para “{term}”"
LIST_MORE = "Mostrar mais ofertas"

# Nenhuma oferta publicada.
EMPTY_TITLE = "Ainda não há ofertas por aqui"
EMPTY_TEXT = "Quando alguém publicar, aparece nesta lista."
EMPTY_ACTION = "Quero vender"

# Busca ou filtro sem resultado.
NO_RESULTS_SEARCH_TITLE = "Nada encontrado para “{term}”"
NO_RESULTS_SEARCH_TEXT = "Confira a escrita ou tente outra palavra."
NO_RESULTS_FILTER_TITLE = "Nada encontrado com estes filtros"
NO_RESULTS_FILTER_TEXT = "Tente outra categoria ou veja todas as ofertas."
NO_RESULTS_TODAY_TITLE = "Ninguém confirmou oferta para hoje ainda"
NO_RESULTS_TODAY_TEXT = "Veja todas as ofertas ou volte mais tarde."
CLEAR_FILTERS = "Limpar filtros"

# Página da oferta ----------------------------------------------------------------
PHOTO_ALT_FIRST = "Foto de {title}"
PHOTO_ALT_OTHER = "Foto {n} de {title}"
OFFER_SOLD_OUT = "Esta oferta está esgotada no momento."
OFFER_SOLD = "Esta oferta já foi vendida."
OFFER_OTHER_FROM_SELLER = "Ver outras ofertas de {name}"
FOOD_NOT_INFORMED = "Não informado pelo vendedor"
FOOD_PORTION = "Porção"
FOOD_INGREDIENTS = "Ingredientes"
FOOD_ALLERGENS = "Alergênicos"

# Oferta indisponível (404 sem dizer o motivo).
UNAVAILABLE_TITLE = "Esta oferta não está mais disponível"
UNAVAILABLE_TEXT = "Ela pode ter sido vendida, pausada ou removida."
UNAVAILABLE_ACTION = "Ver outras ofertas"

# Página do vendedor ------------------------------------------------------------
SELLER_OFFERS_TITLE = "Ofertas de {name}"
SELLER_NO_OFFERS = "{name} não tem ofertas ativas agora."

# Denúncia ----------------------------------------------------------------------
REPORT_REASON_LABEL = "Qual é o problema?"
# Chave = valor de `Report.Reason`. Mesmo sentido dos rótulos que a
# administração vê (`texts/moderation.py::REPORT_REASONS`), escritos para o
# visitante. "Anúncio repetido" (spec) entra em "Outro motivo".
REPORT_REASONS = {
    "misleading": "Parece golpe ou anúncio enganoso",
    "prohibited": "Produto ou serviço proibido ou perigoso",
    "offensive": "Conteúdo ofensivo ou impróprio",
    "unavailable": "Indisponível ou com informação desatualizada",
    "other": "Outro motivo (por exemplo, anúncio repetido)",
}
REPORT_REASON_REQUIRED = "Escolha o motivo da denúncia."
REPORT_REASON_INVALID = "Escolha um dos motivos da lista."
REPORT_DETAILS_LABEL = "Conte mais"
REPORT_DETAILS_HELP = "Não coloque dados pessoais seus. Até 500 caracteres."
REPORT_DETAILS_TOO_LONG = "Escreva no máximo 500 caracteres."
REPORT_RATE_LIMITED = "Você enviou muitas denúncias em pouco tempo. Tente de novo mais tarde."
REPORT_OK = "Recebemos sua denúncia. Obrigado por avisar."
