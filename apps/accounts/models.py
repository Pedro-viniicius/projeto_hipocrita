from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


def normalize_email(email: str) -> str:
    """E-mail sem espaços nas pontas e todo em minúsculas (é o login)."""
    return (email or "").strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra) -> User:
        email = normalize_email(email)
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        user = self.model(email=email, **extra)
        user.set_password(password)  # None gera senha inutilizável
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> User:
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str) -> User:
        return self.get(email=normalize_email(username))


class User(AbstractBaseUser, PermissionsMixin):
    """Conta de acesso. O login é o e-mail; `is_staff` = administrador do site."""

    email = models.EmailField(max_length=254, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def save(self, *args, **kwargs) -> None:
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email(self.email)

    def __str__(self) -> str:
        return f"Usuário {self.pk}"
