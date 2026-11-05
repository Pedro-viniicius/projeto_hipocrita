"""Configuração dos testes: independe do ambiente do container (DEBUG, segredos, S3)."""

import os

# Força valores de produção antes de carregar a configuração base, para que os
# testes vejam cookies Secure etc. mesmo quando o compose define DEBUG=true.
os.environ["DEBUG"] = "false"
os.environ["SECRET_KEY"] = "chave-de-teste-apenas-para-pytest-0123456789-abcdefghijklmnop"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["COMMUNITY_TZ"] = "America/Sao_Paulo"
os.environ.pop("COOKIE_SECURE", None)
os.environ.pop("CSP_EXTRA_IMG_SRC", None)

from config.settings import *  # noqa: E402, F403

ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Sem collectstatic nos testes: o whitenoise lê direto de static/.
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
DEMO_DATA = False
TRUSTED_PROXY_HOPS = 0
LOG_LEVEL = "WARNING"
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
