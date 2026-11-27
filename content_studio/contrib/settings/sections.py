"""
The sections configure() runs. A section is a function that takes a
Context and returns settings; configure() runs them in order. A module
that reads its own environment variables (logging, error reports and the
like) adds a section here, or a project passes its own to configure().
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from .env import (
    Env,
    hostname,
    mail_settings,
    origin,
    parse_cache_url,
    parse_database_url,
    parse_email_url,
)

__all__ = [
    "DEFAULT_IMAGE_SIZES",
    "SECTIONS",
    "Context",
    "Section",
    "cache",
    "content_studio",
    "core",
    "database",
    "mail",
    "security",
    "storage",
    "tasks",
]

DEFAULT_PROJECT_NAME = "content-studio"
DEFAULT_SITE_URL = "http://localhost:8000"

DEFAULT_IMAGE_SIZES = {
    "thumbnail": {"width": 400, "height": 400, "fit": "cover"},
    "card": {"width": 800, "height": 500, "fit": "cover"},
    "content": {"width": 1200},
    "hero": {"width": 2000},
    "share": {"width": 1200, "height": 630, "fit": "cover", "format": "jpeg"},
}

REDIS_SCHEMES = ("redis", "rediss", "valkey", "valkeys")
# The Postgres schemes parse_database_url reads.
POSTGRES_SCHEMES = ("postgres", "postgresql", "pgsql", "postgis")

SQL_HUEY = "content_studio.contrib.settings.huey.SqlHuey"


@dataclass(frozen=True)
class Context:
    """
    What a section reads: the environment, the project, the settings the
    sections before it returned, and the values every section needs.
    """

    env: Env
    base_dir: Path
    # The settings module before configure() ran (its globals()).
    namespace: Mapping[str, Any]
    # What the sections before this one set, read-only.
    settings: Mapping[str, Any]
    debug: bool
    project_name: str
    site_url: str
    backend_url: str

    @property
    def secure(self) -> bool:
        """Whether the site is served over HTTPS (SITE_URL is https)."""
        return self.site_url.startswith("https://")


Section = Callable[[Context], Mapping[str, Any]]


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _scheme(url: str | None) -> str:
    return (url or "").split(":", 1)[0].lower()


def core(ctx: Context) -> dict[str, Any]:
    """DEBUG, SECRET_KEY, the site's URLs, hosts and CSRF origins."""
    # Hosts: the public hosts, the backend's name on a Compose network (a
    # frontend container reaches Django at http://backend:8000) and
    # localhost for health checks.
    hosts = [
        hostname(ctx.site_url),
        hostname(ctx.backend_url),
        "backend",
        "localhost",
        "127.0.0.1",
    ]
    hosts += ctx.env.list("ALLOWED_HOSTS")

    return {
        "DEBUG": ctx.debug,
        "PROJECT_NAME": ctx.project_name,
        "SECRET_KEY": ctx.env.str("DJANGO_SECRET_KEY", required=True),
        "SITE_URL": ctx.site_url,
        "BACKEND_URL": ctx.backend_url,
        "ALLOWED_HOSTS": list(dict.fromkeys(host for host in hosts if host)),
        "CSRF_TRUSTED_ORIGINS": list(
            dict.fromkeys([origin(ctx.site_url), origin(ctx.backend_url)])
        ),
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
    }


def database_url(ctx: Context) -> str:
    """DATABASE_URL, or a SQLite file in the project's base directory."""
    return ctx.env.str("DATABASE_URL") or f"sqlite:///{ctx.base_dir / 'db.sqlite3'}"


def database_pool(database: dict[str, Any], env: Env) -> dict[str, Any]:
    """The DATABASES entry with psycopg's connection pool, for DATABASE_POOL=1."""
    if database["ENGINE"] == "django.db.backends.sqlite3":
        return database

    if not _installed("psycopg_pool"):
        raise ImproperlyConfigured(
            "DATABASE_POOL=1 needs psycopg_pool; install "
            "django-content-studio[server]."
        )

    size = env.int("DATABASE_POOL_SIZE", 4)

    if size is None or size < 1:
        raise ImproperlyConfigured("DATABASE_POOL_SIZE must be 1 or more.")

    options = {
        **database.get("OPTIONS", {}),
        "pool": {"min_size": 1, "max_size": size},
    }
    return {**database, "OPTIONS": options}


def database(ctx: Context) -> dict[str, Any]:
    """DATABASES from DATABASE_URL, with the pool for DATABASE_POOL=1."""
    default = parse_database_url(database_url(ctx))

    if ctx.env.bool("DATABASE_POOL", False):
        default = database_pool(default, ctx.env)

    return {"DATABASES": {"default": default}}


def cache(ctx: Context) -> dict[str, Any]:
    """
    CACHES from CACHE_URL: shared by login limits, ended sessions and
    presence. db:// is a table in the database (made by migrate),
    redis:// or valkey:// a Redis-compatible server.
    """
    url = ctx.env.str("CACHE_URL", "locmem://") or "locmem://"
    return {"CACHES": {"default": parse_cache_url(url, key_prefix=ctx.project_name)}}


def task_settings(
    tasks_url: str | None,
    cache_url: str | None,
    database_url: str,
    project_name: str,
    env: Env,
) -> dict[str, Any]:
    """HUEY and TASKS for a TASKS_URL (or, without one, the cache's Redis)."""
    scheme = _scheme(tasks_url)

    if not scheme:
        if _scheme(cache_url) in REDIS_SCHEMES:
            scheme, tasks_url = "redis", cache_url
        else:
            scheme, tasks_url = "immediate", ""

    immediate = {
        "HUEY": {
            "huey_class": "huey.MemoryHuey",
            "name": project_name,
            "immediate": True,
        },
        "TASKS": {
            "default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}
        },
    }

    if scheme == "immediate" or not _installed("huey"):
        return immediate

    consumer = {"workers": env.int("HUEY_WORKERS", 2), "worker_type": "thread"}

    if scheme in REDIS_SCHEMES:
        huey: dict[str, Any] = {
            "huey_class": "huey.RedisHuey",
            "connection": {"url": str(tasks_url).replace("valkey", "redis", 1)},
        }
    elif scheme == "db":
        database_scheme = _scheme(database_url)

        if database_scheme in POSTGRES_SCHEMES:
            queue_database = "psycopg3:" + database_url.split(":", 1)[1]
        elif database_scheme == "sqlite":
            queue_database = "sqlite:///" + parse_database_url(database_url)["NAME"]
        else:
            raise ImproperlyConfigured(
                "TASKS_URL=db:// needs a postgres:// or sqlite:// DATABASE_URL."
            )

        # Polls the database; migrate creates the huey_* tables.
        huey = {
            "huey_class": SQL_HUEY,
            "database": queue_database,
            "create_tables": False,
        }
    else:
        raise ImproperlyConfigured(
            f"TASKS_URL has an unsupported scheme {scheme!r}; use db://, "
            "redis:// or immediate://."
        )

    return {
        "HUEY": {
            "name": project_name,
            "immediate": False,
            **huey,
            "consumer": consumer,
        },
        "TASKS": {
            "default": {"BACKEND": "huey.contrib.djhuey.tasks_backend.HueyBackend"}
        },
    }


def tasks(ctx: Context) -> dict[str, Any]:
    """
    HUEY and Django's TASKS from TASKS_URL: db:// (tables in the
    database), redis:// or valkey://, or immediate:// (no worker: tasks
    run in the request). Without TASKS_URL, a Redis CACHE_URL is used, and
    otherwise tasks run immediately; so they do without Huey installed.
    """
    url = database_url(ctx)
    result = task_settings(
        ctx.env.str("TASKS_URL"),
        ctx.env.str("CACHE_URL"),
        url,
        ctx.project_name,
        ctx.env,
    )

    # Huey's task statistics in Postgres, so the web and worker
    # containers share them (the default is a SQLite file per container).
    if _scheme(url) in POSTGRES_SCHEMES and "HUEY_STATS" not in ctx.namespace:
        result["HUEY_STATS"] = {"database": "psycopg3:" + url.split(":", 1)[1]}

    return result


def mail(ctx: Context) -> dict[str, Any]:
    """The mailer from EMAIL_URL and the From addresses."""
    result = mail_settings(parse_email_url(ctx.env.str("EMAIL_URL", "console://")))
    host = hostname(ctx.site_url) or "localhost"
    from_email = ctx.env.str(
        "DEFAULT_FROM_EMAIL", f"{ctx.project_name} <noreply@{host}>"
    )
    return {**result, "DEFAULT_FROM_EMAIL": from_email, "SERVER_EMAIL": from_email}


def s3_storage(ctx: Context) -> tuple[dict[str, Any], str | None]:
    """The S3 default storage for S3_BUCKET, and the MEDIA_URL it serves from."""
    env = ctx.env
    options: dict[str, Any] = {
        "bucket_name": env.str("S3_BUCKET"),
        "access_key": env.str("S3_ACCESS_KEY_ID"),
        "secret_key": env.str("S3_SECRET_ACCESS_KEY"),
        "region_name": env.str("S3_REGION"),
        "endpoint_url": env.str("S3_ENDPOINT_URL"),
        "default_acl": None,
        "querystring_auth": env.bool("S3_QUERYSTRING_AUTH", False),
        "file_overwrite": False,
    }
    media_url = None

    # The public base URL of the files, when it isn't the endpoint: a CDN,
    # or http://localhost:8333/media for a development S3 service.
    public_url = (env.str("S3_PUBLIC_URL") or "").rstrip("/")
    custom_domain = env.str("S3_CUSTOM_DOMAIN")

    if public_url:
        scheme, _, rest = public_url.partition("://")
        options["custom_domain"] = rest
        options["url_protocol"] = f"{scheme}:"
        media_url = f"{public_url}/"
    elif custom_domain:
        options["custom_domain"] = custom_domain
        media_url = f"https://{custom_domain}/"

    storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {key: value for key, value in options.items() if value is not None},
    }
    return storage, media_url


def storage(ctx: Context) -> dict[str, Any]:
    """
    Static files and media: STORAGES, MEDIA_URL and MEDIA_ROOT, with S3
    for S3_BUCKET. Static files are collected into <base_dir>/staticfiles
    and served hashed and compressed by WhiteNoise when it is installed
    and DEBUG is off.
    """
    media_url = ctx.env.str("MEDIA_URL", f"{ctx.backend_url}/media/")
    default_storage: dict[str, Any] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage"
    }

    if ctx.env.str("S3_BUCKET"):
        default_storage, s3_media_url = s3_storage(ctx)
        media_url = s3_media_url or media_url

    staticfiles_backend = (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if _installed("whitenoise") and not ctx.debug
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    )

    return {
        "STATIC_URL": "/static/",
        "STATIC_ROOT": ctx.base_dir / "staticfiles",
        "MEDIA_URL": media_url,
        "MEDIA_ROOT": Path(ctx.env.str("MEDIA_ROOT") or ctx.base_dir / "media"),
        "STORAGES": {
            "default": default_storage,
            "staticfiles": {"BACKEND": staticfiles_backend},
        },
    }


def security(ctx: Context) -> dict[str, Any]:
    """
    Proxies, HTTPS, cookies and security headers. TLS ends at the reverse
    proxy, which sets X-Forwarded-Proto.
    """
    env = ctx.env
    secure = ctx.secure
    num_proxies = env.int("NUM_PROXIES", 0)
    s: dict[str, Any] = {}

    if num_proxies:
        s["SECURE_PROXY_SSL_HEADER"] = ("HTTP_X_FORWARDED_PROTO", "https")

    s["SESSION_COOKIE_SECURE"] = secure
    s["CSRF_COOKIE_SECURE"] = secure
    s["SESSION_COOKIE_HTTPONLY"] = True
    s["SESSION_COOKIE_SAMESITE"] = "Lax"
    s["SECURE_CONTENT_TYPE_NOSNIFF"] = True
    s["SECURE_REFERRER_POLICY"] = "strict-origin-when-cross-origin"
    s["X_FRAME_OPTIONS"] = "DENY"

    if secure:
        s["SECURE_HSTS_SECONDS"] = env.int("SECURE_HSTS_SECONDS", 31536000)
        s["SECURE_HSTS_INCLUDE_SUBDOMAINS"] = env.bool(
            "SECURE_HSTS_INCLUDE_SUBDOMAINS", False
        )
        s["SECURE_HSTS_PRELOAD"] = env.bool("SECURE_HSTS_PRELOAD", False)
        # The reverse proxy redirects HTTP to HTTPS; redirecting in Django
        # as well would break health checks on the internal network.
        s["SECURE_SSL_REDIRECT"] = env.bool("SECURE_SSL_REDIRECT", False)

    # Deploy checks that don't apply: the proxy redirects to HTTPS, and
    # HSTS for subdomains or the preload list is a choice for the whole
    # domain, which the two opt-ins make. Content Studio's W040 reports a
    # weak secret key with a hint, in place of Django's W009.
    silenced = list(ctx.namespace.get("SILENCED_SYSTEM_CHECKS", []))
    silenced.append("security.W009")

    if secure:
        silenced += ["security.W005", "security.W021"]

        if num_proxies and not s["SECURE_SSL_REDIRECT"]:
            silenced.append("security.W008")

    s["SILENCED_SYSTEM_CHECKS"] = list(dict.fromkeys(silenced))

    # Content Studio's login limits count per client IP address, which
    # Django REST Framework reads from X-Forwarded-For behind NUM_PROXIES.
    s["REST_FRAMEWORK"] = {"NUM_PROXIES": num_proxies or None}

    return s


def content_studio(ctx: Context) -> dict[str, Any]:
    """
    Content Studio's defaults: the media library, its image sizes (with
    Pillow installed, which makes them) and the admin's URL for emails.
    """
    defaults: dict[str, Any] = {
        "MEDIA_LIBRARY_MODEL": "content_studio.media_library.models.Media",
        "MEDIA_LIBRARY_FOLDER_MODEL": "content_studio.media_library.models.Folder",
        "MEDIA_LIBRARY_MAX_UPLOAD_SIZE": ctx.env.int(
            "MEDIA_MAX_UPLOAD_SIZE", 50 * 1024 * 1024
        ),
        "ADMIN_URL": f"{ctx.backend_url}/admin/",
        # With content_studio.notifications installed: mail editors
        # what they left unread.
        "NOTIFICATION_EMAIL_DIGEST": True,
    }

    # The captcha of content_studio.contrib.captcha: on, or off.
    captcha = ctx.env.str("CAPTCHA", "on")
    if captcha not in ("on", "off"):
        raise ImproperlyConfigured(f"CAPTCHA must be on or off, not {captcha!r}.")
    defaults["CAPTCHA"] = captcha == "on"
    defaults["CAPTCHA_THROTTLE_RATE"] = ctx.env.str(
        "CAPTCHA_THROTTLE_RATE", "30/minute"
    )

    if _installed("PIL"):
        defaults["IMAGE_SIZES"] = deepcopy(DEFAULT_IMAGE_SIZES)

    return {"CONTENT_STUDIO": defaults}


# The built-in sections, in the order configure() runs them.
SECTIONS: list[Section] = [
    core,
    database,
    cache,
    tasks,
    mail,
    storage,
    security,
    content_studio,
]
