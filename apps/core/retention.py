"""Prazos de guarda de dados, usados pelo comando `cleanup_data` e pela página de privacidade.

Mudou um prazo aqui, mudou nos dois lugares.
"""

# Buscas sem resultado (`metrics.DailySearchMiss`): o termo pode ter nome de pessoa.
SEARCH_MISS_DAYS = 90

# Texto livre das denúncias tratadas (`moderation.Report.details`), contado da
# data em que a denúncia foi resolvida. O resto da denúncia fica.
REPORT_DETAILS_DAYS = 180

# Contadores do limite de tentativas (HMAC do IP, do e-mail ou do usuário): prazo
# prometido na página de privacidade.
RATE_LIMIT_HOURS = 24

# Intervalo do cron do `cleanup_data` em produção (README).
CLEANUP_INTERVAL_HOURS = 1

# Idade (contada do início da janela) a partir da qual o contador com dado pessoal é
# apagado. Sem tráfego, só o cron apaga: a linha pode esperar até uma rodada inteira
# depois de vencer, então ela vence uma rodada antes de RATE_LIMIT_HOURS.
RATE_LIMIT_PURGE_HOURS = RATE_LIMIT_HOURS - CLEANUP_INTERVAL_HOURS
