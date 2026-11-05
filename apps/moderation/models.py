from django.conf import settings
from django.db import models
from django.db.models import Q


class Report(models.Model):
    """Denúncia de visitante. Sem IP nem identificação de quem denuncia.

    `details` é texto livre e pode conter dado pessoal de terceiros: só o admin vê.
    """

    class Reason(models.TextChoices):
        MISLEADING = "misleading", "Enganoso"
        PROHIBITED = "prohibited", "Proibido"
        OFFENSIVE = "offensive", "Ofensivo"
        UNAVAILABLE = "unavailable", "Indisponível"
        OTHER = "other", "Outro"

    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        RESOLVED = "resolved", "Tratada"

    offer = models.ForeignKey("catalog.Offer", on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="moderation_report_status")]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    reason__in=["misleading", "prohibited", "offensive", "unavailable", "other"]
                ),
                name="moderation_report_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["open", "resolved"]),
                name="moderation_report_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"Denúncia {self.pk}"
