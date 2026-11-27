"""
Deploy checks of content_studio.contrib.settings (manage.py check --deploy).

- content_studio.E065: DEBUG is on.
- content_studio.W040: SECRET_KEY is a placeholder or too weak. It
  replaces Django's security.W009, which configure() silences.
- content_studio.W041: the default cache isn't shared between processes.
- content_studio.W042: SITE_URL is https, but Django doesn't trust the
  proxy's X-Forwarded-Proto header (NUM_PROXIES is unset).
"""

from django.conf import settings
from django.core import checks

__all__ = [
    "check_cache",
    "check_debug",
    "check_proxy",
    "check_secret_key",
    "is_weak_secret_key",
]

GENERATE_HINT = (
    'Generate one with `python -c "from django.core.management.utils '
    'import get_random_secret_key; print(get_random_secret_key())"` and set '
    "it as DJANGO_SECRET_KEY."
)

# Words in the values that example .env files and tutorials ship with.
PLACEHOLDERS = (
    "change-me",
    "change_me",
    "changeme",
    "replace-me",
    "replace_me",
    "replaceme",
    "placeholder",
    "insecure",
    "example",
    "your-secret",
    "your_secret",
    "secret-key",
    "secret_key",
    "secretkey",
)

MIN_LENGTH = 50
MIN_UNIQUE_CHARACTERS = 5


def is_weak_secret_key(value: str) -> str | None:
    """Why a secret key is unsafe ("placeholder" or "short"), or None."""
    lowered = (value or "").lower()

    if any(word in lowered for word in PLACEHOLDERS):
        return "placeholder"

    if len(value or "") < MIN_LENGTH or len(set(value)) < MIN_UNIQUE_CHARACTERS:
        return "short"

    return None


@checks.register(checks.Tags.security, deploy=True)
def check_debug(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    if not settings.DEBUG:
        return []

    return [
        checks.Error(
            "DEBUG is on.",
            hint="Set DJANGO_DEBUG=0 in production: debug pages show your "
            "settings and source code.",
            id="content_studio.E065",
        )
    ]


@checks.register(checks.Tags.security, deploy=True)
def check_secret_key(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    reason = is_weak_secret_key(getattr(settings, "SECRET_KEY", "") or "")

    if reason == "placeholder":
        message = "DJANGO_SECRET_KEY looks like a placeholder."
    elif reason == "short":
        message = (
            f"DJANGO_SECRET_KEY is shorter than {MIN_LENGTH} characters or has "
            f"fewer than {MIN_UNIQUE_CHARACTERS} different characters."
        )
    else:
        return []

    return [checks.Warning(message, hint=GENERATE_HINT, id="content_studio.W040")]


@checks.register(checks.Tags.caches, deploy=True)
def check_cache(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    from ...health.checks import unshared_cache

    name = unshared_cache()

    if not name:
        return []

    return [
        checks.Warning(
            f"The default cache ({name}) isn't shared between processes, so "
            "login limits, ended sessions and presence are kept per process.",
            hint="Set CACHE_URL to db:// (a table in the database) or a "
            "redis:// or valkey:// server.",
            id="content_studio.W041",
        )
    ]


@checks.register(checks.Tags.security, deploy=True)
def check_proxy(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    site_url = getattr(settings, "SITE_URL", "") or ""

    if not site_url.startswith("https://"):
        return []

    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        return []

    return [
        checks.Warning(
            "SITE_URL is https, but Django doesn't trust the proxy's "
            "X-Forwarded-Proto header, so it doesn't see that requests came "
            "in over HTTPS.",
            hint="Set NUM_PROXIES to the number of proxies in front of Django "
            "(1 behind one reverse proxy), so secure cookies and CSRF checks "
            "see HTTPS.",
            id="content_studio.W042",
        )
    ]
