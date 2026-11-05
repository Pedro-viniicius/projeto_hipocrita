from django.db import models


class RateLimitCounter(models.Model):
    """Contador do limite de tentativas.

    Guarda só o HMAC (SHA-256 com a SECRET_KEY) do IP, do e-mail ou do usuário,
    nunca o valor puro. As linhas vencidas são apagadas a cada gravação e pelo
    `cleanup_data` (prazos em `apps.core.ratelimit.purge_old`).
    """

    scope = models.CharField(max_length=20)
    key_hash = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key_hash", "window_start"], name="core_ratelimit_unique_window"
            )
        ]
        indexes = [models.Index(fields=["window_start"], name="core_ratelimit_window_idx")]

    def __str__(self) -> str:
        return f"{self.scope} @ {self.window_start:%Y-%m-%d %H:%M}"
