"""
The health checks: the database, the cache and the worker. Each answers
ok, error or off, and only error makes a site unhealthy. The health
endpoints and the system status page both use them.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .._types import StrOrPromise

logger = logging.getLogger(__name__)

OK = "ok"
ERROR = "error"
OFF = "off"

# Cache backends that live in one process, or store nothing: a heartbeat
# a worker writes there can't be read by the web process.
UNSHARED_CACHES = {
    "django.core.cache.backends.locmem.LocMemCache": _("Local memory"),
    "django.core.cache.backends.dummy.DummyCache": _("Dummy cache"),
}


@dataclass(frozen=True)
class CheckResult:
    """
    How a check went: status is "ok", "error" or "off"; message says
    why for error and off. The health endpoints only show the status.
    """

    status: str = OK
    message: StrOrPromise = ""


def describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".rstrip(": ")


def check_database(alias: str = "default") -> CheckResult:
    """A SELECT 1 on the database."""
    from django.db import connections

    try:
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        logger.warning("Health check of database %r failed.", alias, exc_info=True)
        return CheckResult(ERROR, describe(exc))

    return CheckResult(OK)


def check_cache() -> CheckResult:
    """A value stored in the default cache and read back; off for DummyCache."""
    from django.core.cache import DEFAULT_CACHE_ALIAS, caches
    from django.core.cache.backends.dummy import DummyCache

    cache = caches[DEFAULT_CACHE_ALIAS]

    if isinstance(cache, DummyCache):
        return CheckResult(OFF, _("The dummy cache stores nothing."))

    key = f"content_studio.health.check.{uuid.uuid4().hex}"

    try:
        cache.set(key, "1", 30)
        stored = cache.get(key)
        cache.delete(key)
    except Exception as exc:
        logger.warning("Health check of the cache failed.", exc_info=True)
        return CheckResult(ERROR, describe(exc))

    if stored != "1":
        return CheckResult(ERROR, _("A value that was stored could not be read back."))
    return CheckResult(OK)


def unshared_cache() -> Optional[StrOrPromise]:
    """The name of the default cache when processes can't share it, else None."""
    from django.core.cache import DEFAULT_CACHE_ALIAS, caches

    backend = type(caches[DEFAULT_CACHE_ALIAS])
    return UNSHARED_CACHES.get(f"{backend.__module__}.{backend.__qualname__}")


def stale_after() -> timedelta:
    from ..settings import cs_settings

    return timedelta(seconds=cs_settings.HEALTH_WORKER_STALE_AFTER)


def check_worker() -> CheckResult:
    """
    Whether a worker beat in the last HEALTH_WORKER_STALE_AFTER seconds;
    off when there is no worker to watch (see heartbeat.get_off_reason).
    """
    from . import heartbeat

    try:
        reason = heartbeat.get_off_reason()

        if reason:
            return CheckResult(OFF, reason)

        last = heartbeat.get_last_beat()
    except Exception as exc:
        logger.warning("Health check of the worker failed.", exc_info=True)
        return CheckResult(ERROR, describe(exc))

    if last is None:
        return CheckResult(
            ERROR, _("No heartbeat from a worker yet. Is the worker running?")
        )

    age = timezone.now() - last

    if age > stale_after():
        return CheckResult(
            ERROR,
            _("No heartbeat for %(minutes)s minutes. Is the worker running?")
            % {"minutes": int(age.total_seconds() // 60)},
        )
    return CheckResult(OK)
