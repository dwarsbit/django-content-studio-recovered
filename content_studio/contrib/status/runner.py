"""
Runs the registered services' checks and remembers the results.

Checks run when the status page asks, side by side, each with its own
time limit. The results are kept in the cache for
CONTENT_STUDIO["STATUS_CACHE_TIMEOUT"] seconds, so opening the page (or
the menu's dot asking) repeatedly does not check again every time.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from django.apps import apps
from django.utils import timezone
from django.utils.translation import gettext as _

from ...settings import cs_settings
from .registry import Service, ServiceResult, ServiceStatus, get_services

logger = logging.getLogger(__name__)

CACHE_KEY = "content_studio.status.services"
MAX_WORKERS = 8
STATUSES = {status.value for status in ServiceStatus}


def app_name(module: str):
    """The name of the app a module belongs to, or None."""
    config = apps.get_containing_app_config(module or "")
    return None if config is None else config.verbose_name


def run_check(service: Service) -> tuple[ServiceResult, float]:
    """A service's result and the seconds its check took, in its thread."""
    from django.db import connections

    started = time.monotonic()

    try:
        result = service.check()

        if result is None:
            result = ServiceResult()
        elif not isinstance(result, ServiceResult) or result.status not in STATUSES:
            raise TypeError(
                f"The check of {service.key!r} returned {result!r}; expected "
                f"status.ok(), degraded(), down() or unknown()."
            )
    except Exception as exc:
        logger.warning("Status check %s failed.", service.key, exc_info=True)
        result = ServiceResult(
            ServiceStatus.DOWN, "", f"{type(exc).__name__}: {exc}".rstrip(": ")
        )
    finally:
        # The thread's own database connections end with it.
        connections.close_all()

    return result, time.monotonic() - started


def serialize(service: Service, result: ServiceResult, seconds: float) -> dict:
    group = service.group or app_name(getattr(service.check, "__module__", ""))

    return {
        "key": service.key,
        "label": str(service.label),
        "group": str(group) if group else "",
        "icon": service.icon,
        "url": service.url,
        "status": str(result.status),
        "detail": str(result.detail or ""),
        "message": str(result.message or ""),
        "duration": round(seconds * 1000),
    }


def overall_status(services: list[dict]) -> str:
    statuses = {service["status"] for service in services}

    for status in (ServiceStatus.DOWN, ServiceStatus.DEGRADED):
        if status in statuses:
            return str(status)
    return str(ServiceStatus.OK)


def check_services() -> dict:
    services = get_services()
    rows = []

    if services:
        executor = ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS, len(services)),
            thread_name_prefix="content-studio-status",
        )
        started = time.monotonic()
        futures = [
            (service, executor.submit(run_check, service)) for service in services
        ]

        for service, future in futures:
            # Every check started together: what is left of its limit.
            left = max(service.timeout - (time.monotonic() - started), 0)

            try:
                result, seconds = future.result(timeout=left)
            except FutureTimeout:
                future.cancel()
                result = ServiceResult(
                    ServiceStatus.DOWN,
                    "",
                    _("No answer within %(seconds)s seconds.")
                    % {"seconds": f"{service.timeout:g}"},
                )
                seconds = service.timeout

            rows.append(serialize(service, result, seconds))

        # A check past its limit is left to finish on its own.
        executor.shutdown(wait=False)

    return {
        "checked_at": timezone.now().isoformat(),
        "status": overall_status(rows),
        "services": rows,
    }


def get_status(force: bool = False) -> dict:
    """
    The services' results: the remembered ones while they are fresh,
    unless `force` asks for a new check.
    """
    from django.core.cache import cache

    timeout = cs_settings.STATUS_CACHE_TIMEOUT

    if not force and timeout:
        try:
            cached = cache.get(CACHE_KEY)
        except Exception:
            cached = None

        if cached is not None:
            return cached

    result = check_services()

    if timeout:
        try:
            cache.set(CACHE_KEY, result, timeout)
        except Exception:
            # The cache being down is one of the things reported.
            pass

    return result
