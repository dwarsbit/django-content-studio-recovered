"""
The worker heartbeat: a task that stamps the time in the cache every
minute, and once when a worker starts. The worker check, the status
page's Worker row and content_studio_worker_alive read the stamp.

The task runs through the task adapters (content_studio.dashboard.tasks):
the Huey adapter schedules it on Huey's consumer. With a backend whose
adapter can't schedule tasks, call beat() every minute from the
project's own scheduler.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any, Optional

from django.utils.translation import gettext_lazy as _

from .._types import StrOrPromise

logger = logging.getLogger(__name__)

# The task's key on the task backend, and the cache key of the stamp.
HEARTBEAT_TASK = "content_studio.health.heartbeat"
CACHE_KEY = "content_studio.health.worker"
INTERVAL_MINUTES = 1

# The adapters the heartbeat is scheduled on.
_connected: list[Any] = []


def beat() -> None:
    """Record that a worker is alive, now."""
    from django.core.cache import cache

    cache.set(CACHE_KEY, time.time(), None)


def get_last_beat() -> Optional[datetime]:
    """When a worker last beat, or None when none has."""
    from django.core.cache import cache

    stamp = cache.get(CACHE_KEY)
    return None if stamp is None else datetime.fromtimestamp(stamp, tz=UTC)


def get_adapters() -> list[Any]:
    from ..contrib.status.tasks import get_adapters

    return get_adapters()


def runs_in_request(adapter) -> bool:
    return adapter.implements("runs_in_request") and bool(adapter.runs_in_request())


def connect(adapter) -> bool:
    """
    Schedule the heartbeat on an adapter's workers, when it can schedule
    tasks, the cache is shared and tasks don't run in the request.
    Whether it is scheduled.
    """
    from .checks import unshared_cache

    if any(adapter is known for known in _connected):
        return True

    if (
        not adapter.implements("register_periodic_task")
        or unshared_cache()
        or runs_in_request(adapter)
    ):
        return False

    adapter.register_periodic_task(
        HEARTBEAT_TASK, beat, minutes=INTERVAL_MINUTES, hidden=True
    )

    if adapter.implements("on_worker_startup"):
        adapter.on_worker_startup(HEARTBEAT_TASK, beat)

    _connected.append(adapter)
    return True


def connect_adapters() -> None:
    """Schedule the heartbeat on the task adapters; never fails startup."""
    for adapter in get_adapters():
        try:
            connect(adapter)
        except Exception:
            logger.warning(
                "Could not schedule the worker heartbeat on %s.",
                type(adapter).__name__,
                exc_info=True,
            )


def get_off_reason() -> Optional[StrOrPromise]:
    """
    Why the worker check is off, or None when a worker should be beating:
    the cache can't be shared, tasks run in the request, or nothing
    schedules the heartbeat (and beat() was never called).
    """
    from .checks import unshared_cache

    name = unshared_cache()

    if name:
        return _(
            "The cache (%(name)s) isn't shared between processes, so a "
            "worker's heartbeat can't be seen."
        ) % {"name": name}

    adapters = get_adapters()

    if any(runs_in_request(adapter) for adapter in adapters):
        return _("Tasks run in the request, so there is no worker.")

    schedules = any(
        adapter.implements("register_periodic_task") for adapter in adapters
    )

    if not schedules and get_last_beat() is None:
        if not adapters:
            return _("No task backend connected.")
        return _("The task backend doesn't send a heartbeat.")

    return None
