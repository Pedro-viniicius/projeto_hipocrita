"""Apaga dados que passaram do prazo de guarda (ver `apps/core/retention.py`).

- sessões vencidas (`clearsessions` do Django);
- contadores do limite de tentativas vencidos: com dado pessoal, a partir de
  `RATE_LIMIT_PURGE_HOURS` (uma rodada antes das `RATE_LIMIT_HOURS` prometidas); do
  site inteiro (teto de cadastros), quando a janela de 24 h acaba;
- buscas sem resultado com mais de `SEARCH_MISS_DAYS` dias;
- texto livre (`details`) das denúncias resolvidas há mais de `REPORT_DETAILS_DAYS`
  dias. Motivo, estado e datas ficam.

Roda no `docker/start.sh` a cada subida e, em produção, deve rodar num cron de hora em
hora (README) para cumprir os prazos prometidos na página de privacidade.
Idempotente. A saída só tem contagens, nunca o conteúdo apagado.
"""

from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core import clock, ratelimit, retention
from apps.metrics.models import DailySearchMiss
from apps.moderation.models import Report


class Command(BaseCommand):
    help = "Apaga sessões vencidas e dados que passaram do prazo de guarda."

    def handle(self, *args, **options) -> None:
        now = clock.now()
        today = now.astimezone(clock.community_tz()).date()

        call_command("clearsessions")
        with transaction.atomic():
            counters = ratelimit.purge_old(now)
            misses, _ = DailySearchMiss.objects.filter(
                date__lt=today - timedelta(days=retention.SEARCH_MISS_DAYS)
            ).delete()
            reports = (
                Report.objects.filter(
                    status=Report.Status.RESOLVED,
                    resolved_at__lt=now - timedelta(days=retention.REPORT_DETAILS_DAYS),
                )
                .exclude(details="")
                .update(details="")
            )

        self.stdout.write(
            "Limpeza concluída: sessões vencidas removidas; "
            f"{counters} contador(es) de tentativas, {misses} busca(s) sem resultado "
            f"e o texto de {reports} denúncia(s) tratada(s) apagados."
        )
