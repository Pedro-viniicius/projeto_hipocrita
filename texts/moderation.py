"""Textos de interface da administração (aprovações, anúncios, denúncias e categorias).

Nascem no Python (rótulos e erros de formulário, mensagens de feedback). O texto
fixo das páginas fica nos templates de `templates/moderation/` e `templates/metrics/`.
O designer pode mudar o texto; os nomes das constantes não mudam.
"""

# Mensagens de feedback -------------------------------------------------------
SAVED = "Pronto. Alteração salva."
OFFER_APPROVED = "Anúncio aprovado. Os próximos anúncios desse vendedor já saem publicados."
OFFER_HIDDEN = "Anúncio ocultado. Ele saiu da vitrine."
OFFER_SHOWN = "Anúncio visível de novo."
REPORT_RESOLVED = "Denúncia marcada como tratada."
REPORT_RESOLVED_AND_HIDDEN = "Denúncia tratada e anúncio ocultado."
CATEGORY_CREATED = "Categoria criada."
CATEGORY_HIDDEN = (
    "Categoria escondida: o botão dela sumiu da vitrine, "
    "mas os anúncios dela continuam em “Tudo” e na busca."
)
CATEGORY_SHOWN = "Categoria visível na vitrine."

# Ocultar anúncio -------------------------------------------------------------
HIDE_REASON_LABEL = "Motivo"
HIDE_REASON_HELP = "Fica só para a administração. Exemplo: foto com dado pessoal."
HIDE_REASON_TOO_LONG = "Escreva o motivo em até 200 caracteres."
# Motivo gravado quando o anúncio é ocultado a partir de uma denúncia.
HIDE_REASON_FROM_REPORT = "Denúncia: {reason}"

# Denúncias -------------------------------------------------------------------
# Rótulo de cada motivo (`Report.Reason`) como o admin vê na lista.
REPORT_REASONS = {
    "misleading": "Enganoso ou golpe",
    "prohibited": "Produto ou serviço proibido ou perigoso",
    "offensive": "Conteúdo ofensivo ou impróprio",
    "unavailable": "Indisponível ou desatualizado",
    "other": "Outro motivo",
}

# Categorias ------------------------------------------------------------------
CATEGORY_NAME_LABEL = "Nome"
CATEGORY_NAME_HELP = "Exemplo: Livros e apostilas"
CATEGORY_POSITION_LABEL = "Posição"
CATEGORY_POSITION_HELP = "Menor número aparece primeiro."
CATEGORY_IS_FOOD_LABEL = "É alimento (pede porção, ingredientes e alergênicos)"
CATEGORY_REQUIRED = "Preencha este campo."
CATEGORY_NAME_INVALID = "Digite um nome com pelo menos uma letra ou número."
CATEGORY_NAME_TAKEN = "Já existe uma categoria com esse nome."
CATEGORY_POSITION_INVALID = "Digite um número inteiro de 0 a 999."
