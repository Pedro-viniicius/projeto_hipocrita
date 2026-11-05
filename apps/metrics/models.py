"""Métricas agregadas por dia (CA16).

Nenhuma tabela guarda IP, User-Agent, cookie, sessão ou usuário: só contagens
por dia e por oferta, e o termo de busca já normalizado.
"""

from django.db import models


class DailyOfferStat(models.Model):
    date = models.DateField()
    offer = models.ForeignKey("catalog.Offer", on_delete=models.CASCADE, related_name="daily_stats")
    views = models.PositiveIntegerField(default=0)
    whatsapp_clicks = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["date", "offer"], name="metrics_offerstat_unique_day")
        ]

    def __str__(self) -> str:
        return f"{self.date} · anúncio {self.offer_id}"


class DailySearchMiss(models.Model):
    """Busca sem resultado: termo normalizado (até 60 caracteres) e quantas vezes no dia."""

    date = models.DateField()
    term = models.CharField(max_length=60)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date", "-count"]
        constraints = [
            models.UniqueConstraint(fields=["date", "term"], name="metrics_searchmiss_unique_day")
        ]

    def __str__(self) -> str:
        return f"{self.date} · {self.term}"
