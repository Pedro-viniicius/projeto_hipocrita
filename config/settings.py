"""Configuração do Django. Tudo o que muda por ambiente vem de variáveis (ver `.env.example`)."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.exceptions import ImproperlyConfigured

from config import env as envlib

ENV = os.environ
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = envlib.env_bool(ENV, "DEBUG", False)

SECRET_KEY = ENV.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Defina SECRET_KEY (obrigatória com DEBUG=false).")
    # Só para desenvolvimento local; nunca vale com DEBUG=false.
    SECRET_KEY = "dev-only-chave-insegura-nao-use-em-producao"  # noqa: S105

ALLOWED_HOSTS = envlib.env_list(
    ENV, "ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"] if DEBUG else []
)
CSRF_TRUSTED_ORIGINS = envlib.env_list(ENV, "CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.forms",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.moderation",
    "apps.metrics",
]

MIDDLEWARE = [
    "apps.core.middleware.HealthzMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.RequestSizeLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
FORM_RENDERER = "apps.core.forms.AccessibleFormRenderer"

DATABASES = envlib.build_databases(ENV, BASE_DIR)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "seller:dashboard"
LOGOUT_REDIRECT_URL = "catalog:home"

# Idioma e fuso. O banco guarda UTC; "hoje" e "agora" usam COMMUNITY_TZ.
LANGUAGE_CODE = "pt-br"
USE_I18N = True
USE_TZ = True
COMMUNITY_TZ = envlib.env_str(ENV, "COMMUNITY_TZ", "America/Sao_Paulo")
try:
    ZoneInfo(COMMUNITY_TZ)
except Exception as exc:  # ZoneInfoNotFoundError ou nome inválido
    raise ImproperlyConfigured("COMMUNITY_TZ não é um fuso válido.") from exc
TIME_ZONE = COMMUNITY_TZ

# Arquivos estáticos (whitenoise) e mídia (fotos dos anúncios).
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(envlib.env_str(ENV, "MEDIA_ROOT") or BASE_DIR / "media")
STORAGE_BACKEND = envlib.env_str(ENV, "STORAGE_BACKEND", "local").lower()
STORAGES = envlib.build_storages(ENV, MEDIA_ROOT)

# Fotos: limites usados por apps/catalog/imaging.py e photos.py.
MAX_UPLOAD_MB = envlib.env_int(ENV, "MAX_UPLOAD_MB", 5)
MAX_PHOTOS_PER_OFFER = 3
# Teto do corpo de qualquer requisição (Content-Length): as fotos de um anúncio
# mais 1 MB de folga para os campos de texto. Acima disso, 413.
MAX_REQUEST_BODY_BYTES = (MAX_PHOTOS_PER_OFFER * MAX_UPLOAD_MB + 1) * 1024 * 1024

# Regras do produto.
RECONFIRM_DAYS = envlib.env_int(ENV, "RECONFIRM_DAYS", 14)
DEMO_DATA = envlib.env_bool(ENV, "DEMO_DATA", False)
# Teto de contas novas por dia, somando todos os visitantes (0 fecha o cadastro).
SIGNUPS_PER_DAY = envlib.env_int(ENV, "SIGNUPS_PER_DAY", 50)
if SIGNUPS_PER_DAY < 0:
    raise ImproperlyConfigured("SIGNUPS_PER_DAY deve ser 0 ou mais.")

# Página de privacidade (LGPD art. 9): quem responde pelos dados e como falar com ele.
# Vazias, a página mostra "a definir" e `check --deploy` avisa (core.W001).
PRIVACY_CONTROLLER_NAME = envlib.env_str(ENV, "PRIVACY_CONTROLLER_NAME")
PRIVACY_CONTACT_EMAIL = envlib.env_str(ENV, "PRIVACY_CONTACT_EMAIL")

# Limite de tentativas: quantos proxies confiáveis ficam na frente do app.
TRUSTED_PROXY_HOPS = envlib.env_int(ENV, "TRUSTED_PROXY_HOPS", 0)

# Sessão, CSRF e HTTPS.
_security = envlib.security_settings(ENV, debug=DEBUG)
SESSION_COOKIE_HTTPONLY = _security["SESSION_COOKIE_HTTPONLY"]
SESSION_COOKIE_SAMESITE = _security["SESSION_COOKIE_SAMESITE"]
SESSION_COOKIE_SECURE = _security["SESSION_COOKIE_SECURE"]
CSRF_COOKIE_HTTPONLY = _security["CSRF_COOKIE_HTTPONLY"]
CSRF_COOKIE_SAMESITE = _security["CSRF_COOKIE_SAMESITE"]
CSRF_COOKIE_SECURE = _security["CSRF_COOKIE_SECURE"]
SECURE_PROXY_SSL_HEADER = _security["SECURE_PROXY_SSL_HEADER"]
SECURE_SSL_REDIRECT = _security["SECURE_SSL_REDIRECT"]
SECURE_HSTS_SECONDS = _security["SECURE_HSTS_SECONDS"]
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
CONTENT_SECURITY_POLICY = envlib.build_csp(envlib.storage_image_origins(ENV))
# HSTS com subdomínios e preload depende do domínio de cada instalação (ver README).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# E-mail (recuperação de senha). Sem SMTP configurado, vai para o console, e aí
# a recuperação só funciona com DEBUG=true: em produção o link iria para o log
# (ver apps/accounts/views.py, `password_reset_enabled`).
EMAIL_BACKEND = envlib.env_str(
    ENV, "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = envlib.env_str(ENV, "EMAIL_HOST")
EMAIL_PORT = envlib.env_int(ENV, "EMAIL_PORT", 587)
EMAIL_HOST_USER = envlib.env_str(ENV, "EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = ENV.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = envlib.env_bool(ENV, "EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = envlib.env_str(ENV, "DEFAULT_FROM_EMAIL", "nao-responda@localhost")

# Logs: nunca em DEBUG para o banco (as queries trazem parâmetros com dado pessoal);
# exceções de banco saem sem a mensagem (ver apps/core/logging.py) e o caminho
# /senha/redefinir/<uid>/<token>/ sai mascarado (apps/core/redaction.py).
LOG_LEVEL = envlib.env_str(ENV, "LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_db_errors": {"()": "apps.core.logging.RedactDatabaseErrors"},
        "redact_reset_links": {"()": "apps.core.redaction.RedactPasswordResetLinks"},
    },
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["redact_db_errors", "redact_reset_links"],
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
if not DEBUG:
    # Host fora de ALLOWED_HOSTS é ruído de robô: sem traceback no log de produção.
    LOGGING["handlers"]["null"] = {"class": "logging.NullHandler"}
    LOGGING["loggers"]["django.security.DisallowedHost"] = {
        "handlers": ["null"],
        "propagate": False,
    }
