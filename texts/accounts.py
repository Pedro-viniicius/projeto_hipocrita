"""Textos de interface das contas: cadastro, login, senha e exclusão de conta.

Nascem no Python (rótulos, dicas e erros de formulário, mensagens de feedback).
O designer pode mudar o texto; os nomes das constantes não mudam.
"""

# S105 (senha fixa no código) é falso positivo aqui: as constantes com
# "PASSWORD" no nome são rótulos e mensagens de interface, não senhas.
# ruff: noqa: S105

# Campos ----------------------------------------------------------------------
EMAIL_LABEL = "E-mail"
PASSWORD_LABEL = "Senha"
PASSWORD_HELP = "Mínimo de 8 caracteres."
NAME_LABEL = "Nome ou marca"
NAME_HELP = "Exemplo: Doces da Ana"
WHATSAPP_LABEL = "WhatsApp com DDD"
WHATSAPP_HELP = (
    "Exemplo: (35) 91234-5678. Só você e a administração veem o número. "
    "Se você autorizar, quem tocar em “Consultar no WhatsApp” abre a conversa com você."
)
WHATSAPP_PUBLIC_LABEL = "Mostrar meu WhatsApp para quem quer comprar"
WHATSAPP_PUBLIC_HELP = (
    "Sem isso, seus anúncios não aparecem na vitrine. "
    "Você pode mudar isso a qualquer momento no Perfil."
)

NEW_PASSWORD_LABEL = "Nova senha"
NEW_PASSWORD_CONFIRM_LABEL = "Repita a nova senha"
OLD_PASSWORD_LABEL = "Senha atual"
DELETE_PASSWORD_LABEL = "Digite sua senha para confirmar"

# Erros -----------------------------------------------------------------------
REQUIRED = "Preencha este campo."
EMAIL_INVALID = "Digite um e-mail válido. Exemplo: ana@email.com"
EMAIL_TAKEN = "Já existe uma conta com este e-mail. Tente entrar."
PASSWORD_TOO_SHORT = "A senha precisa ter pelo menos 8 caracteres."
WHATSAPP_INVALID = "Digite um WhatsApp válido com DDD. Exemplo: (35) 91234-5678"
NAME_INVALID = "Digite um nome com pelo menos uma letra ou número."
LOGIN_FAILED = "E-mail ou senha incorretos. Confira e tente de novo."
LOGIN_RATE_LIMITED = "Muitas tentativas. Espere alguns minutos e tente de novo."
DELETE_WRONG_PASSWORD = "Senha incorreta. Confira e tente de novo."
DELETE_RATE_LIMITED = "Muitas tentativas. Espere alguns minutos e tente de novo."
SIGNUP_DAILY_LIMIT = "Os cadastros de hoje já se esgotaram. Tente de novo amanhã."
# Com SIGNUPS_PER_DAY=0 não há data para reabrir: nada de "hoje" nem "amanhã".
SIGNUP_CLOSED = "O cadastro de novos vendedores está fechado."

# Mensagens de feedback -------------------------------------------------------
SIGNUP_OK = "Conta criada. Agora é só adicionar seu primeiro anúncio."
PASSWORD_CHANGED = "Senha alterada."
ACCOUNT_DELETED = "Sua conta foi excluída. Seus anúncios saíram da vitrine."

# E-mail de recuperação de senha (assunto; o corpo fica no template .txt).
PASSWORD_RESET_SUBJECT = "Redefinir sua senha no Pão de Cada Dia"
