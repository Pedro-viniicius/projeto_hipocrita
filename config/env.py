"""Leitura de variáveis de ambiente e montagem das partes da configuração.

Funções puras (recebem o ambiente como dicionário) para que a escolha de banco,
de storage, de segurança e do CSP possa ser testada sem recarregar `settings`.
"""

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

TRUE_VALUES = {"1", "true", "t", "yes", "y", "sim", "s", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "nao", "não", "off"}

# Em todas as funções, variável ausente ou em branco ("VAR=" no .env) vale o padrão.


def env_str(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or "").strip() or default


def env_bool(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = (env.get(name) or "").strip().lower()
    if not value:
        return default
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(f"{name} deve ser true ou false.")


def env_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} deve ser um número inteiro.") from exc


def env_list(env: Mapping[str, str], name: str, default: list[str] | None = None) -> list[str]:
    items = [item.strip() for item in (env.get(name) or "").split(",") if item.strip()]
    return items or list(default or [])


def build_databases(env: Mapping[str, str], base_dir: Path) -> dict:
    """PostgreSQL quando `POSTGRES_HOST` está definido; senão SQLite (só testes locais)."""
    host = env_str(env, "POSTGRES_HOST")
    if not host:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": env_str(env, "SQLITE_PATH") or str(base_dir / "db.sqlite3"),
            }
        }
    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": host,
            "PORT": env_str(env, "POSTGRES_PORT", "5432"),
            "NAME": env_str(env, "POSTGRES_DB", "paodecadadia"),
            "USER": env_str(env, "POSTGRES_USER", "paodecadadia"),
            "PASSWORD": env.get("POSTGRES_PASSWORD", ""),
            "CONN_MAX_AGE": env_int(env, "DB_CONN_MAX_AGE", 60),
            "CONN_HEALTH_CHECKS": True,
            # Pooler em modo transação (PgBouncer, Neon): um cursor no servidor
            # não sobrevive à troca de conexão entre transações.
            "DISABLE_SERVER_SIDE_CURSORS": env_bool(env, "DB_DISABLE_SERVER_SIDE_CURSORS", False),
        }
    }


def build_storages(env: Mapping[str, str], media_root: Path) -> dict:
    """Storage das fotos: `local` (disco, padrão) ou `s3` (django-storages)."""
    backend = env_str(env, "STORAGE_BACKEND", "local").lower()
    staticfiles = {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
    if backend == "local":
        return {
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": str(media_root), "base_url": "/media/"},
            },
            "staticfiles": staticfiles,
        }
    if backend == "s3":
        bucket = env_str(env, "AWS_STORAGE_BUCKET_NAME")
        if not bucket:
            raise ImproperlyConfigured("STORAGE_BACKEND=s3 exige AWS_STORAGE_BUCKET_NAME.")
        # As credenciais (AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY) são lidas pelo
        # boto3 direto do ambiente; não passam pela configuração do Django.
        # `security_token: None`: a chave é estática. Sem isso, o django-storages
        # leria um AWS_SESSION_TOKEN que a plataforma (ex.: Vercel) ponha no
        # ambiente e o mandaria junto com a chave do bucket, e o R2 recusaria.
        options = {
            "security_token": None,
            "bucket_name": bucket,
            "region_name": env_str(env, "AWS_S3_REGION_NAME") or None,
            "endpoint_url": env_str(env, "AWS_S3_ENDPOINT_URL") or None,
            "custom_domain": env_str(env, "AWS_S3_CUSTOM_DOMAIN") or None,
            "querystring_auth": env_bool(env, "AWS_QUERYSTRING_AUTH", True),
            "querystring_expire": env_int(env, "AWS_QUERYSTRING_EXPIRE", 3600),
            "file_overwrite": False,
            "default_acl": None,
        }
        return {
            "default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": options},
            "staticfiles": staticfiles,
        }
    raise ImproperlyConfigured("STORAGE_BACKEND deve ser local ou s3.")


def storage_image_origins(env: Mapping[str, str]) -> list[str]:
    """Origens extras de imagem para o CSP quando as fotos vêm do S3."""
    origins: list[str] = []
    if env_str(env, "STORAGE_BACKEND", "local").lower() == "s3":
        custom_domain = env_str(env, "AWS_S3_CUSTOM_DOMAIN")
        endpoint = env_str(env, "AWS_S3_ENDPOINT_URL")
        bucket = env_str(env, "AWS_STORAGE_BUCKET_NAME")
        region = env_str(env, "AWS_S3_REGION_NAME")
        if custom_domain:
            origins.append(f"https://{custom_domain}")
        elif endpoint:
            parts = urlsplit(endpoint)
            origins.append(f"{parts.scheme}://{parts.netloc}")
            origins.append(f"{parts.scheme}://*.{parts.netloc}")
        elif bucket:
            origins.append(f"https://{bucket}.s3.amazonaws.com")
            if region:
                origins.append(f"https://{bucket}.s3.{region}.amazonaws.com")
    origins.extend(env_list(env, "CSP_EXTRA_IMG_SRC"))
    return origins


def build_csp(img_origins: list[str]) -> str:
    """Content-Security-Policy: nada inline; formulários só para o site e o WhatsApp.

    `form-action` inclui o WhatsApp porque o Chrome aplica a diretiva também ao
    redirecionamento que segue o envio do formulário "Consultar no WhatsApp".
    """
    img_src = " ".join(["'self'", "data:", *img_origins])
    directives = [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        f"img-src {img_src}",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self' https://wa.me https://api.whatsapp.com",
    ]
    return "; ".join(directives)


def security_settings(env: Mapping[str, str], *, debug: bool) -> dict:
    """Cookies e HTTPS. Fora do DEBUG os cookies são `Secure` por padrão."""
    secure_default = not debug
    proxy_ssl = env_bool(env, "SECURE_PROXY_SSL_HEADER", False)
    return {
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": env_bool(env, "COOKIE_SECURE", secure_default),
        "CSRF_COOKIE_HTTPONLY": True,
        "CSRF_COOKIE_SAMESITE": "Lax",
        "CSRF_COOKIE_SECURE": env_bool(env, "COOKIE_SECURE", secure_default),
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https") if proxy_ssl else None,
        "SECURE_SSL_REDIRECT": env_bool(env, "SECURE_SSL_REDIRECT", False),
        "SECURE_HSTS_SECONDS": env_int(env, "SECURE_HSTS_SECONDS", 0),
    }
