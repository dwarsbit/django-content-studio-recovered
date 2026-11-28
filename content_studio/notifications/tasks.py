"""
The notification digest and pruning on Huey's worker: when Huey is
installed (huey.contrib.djhuey), two periodic tasks run the commands
that otherwise run from cron.

- notification_digest, every hour at :10, runs
  content_studio_send_notification_digest when the digest is on
  (NOTIFICATION_EMAIL_DIGEST and ADMIN_URL).
- notification_pruning, daily at 04:30, runs
  content_studio_prune_notifications (NOTIFICATION_RETENTION and
  NOTIFICATION_UNREAD_RETENTION).

Each runs under a Huey lock, so two workers never run it at once, with
fresh database connections, so it works with any Huey storage. The times
follow Huey's utc setting (UTC by default). The commands record their
last run for the system status page, from Huey or cron alike.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.core.management import call_command
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("content_studio.notifications")

__all__ = [
    "DIGEST_TASK",
    "PRUNING_TASK",
    "get_last_run",
    "notification_digest",
    "notification_pruning",
    "record_run",
    "register_periodic_tasks",
    "register_status",
]

# The tasks' dotted paths: Huey's names for them, the status page's keys
# and the commands' last run records.
DIGEST_TASK = f"{__name__}.notification_digest"
PRUNING_TASK = f"{__name__}.notification_pruning"

# The schedules (the status page says them in words).
DIGEST_MINUTE = "10"
PRUNING_HOUR, PRUNING_MINUTE = "4", "30"

# The Huey queue the tasks were registered on, once registered.
_registered = None


def notification_digest() -> bool:
    """Email editors their unread notifications. Whether it ran."""
    from .digest import digest_available

    if not digest_available():
        return False

    call_command("content_studio_send_notification_digest", verbosity=0)
    return True


def notification_pruning() -> bool:
    """Remove old notifications, follows and subscriptions. Whether it ran."""
    call_command("content_studio_prune_notifications", verbosity=0)
    return True


def register_periodic_tasks(huey=None):
    """
    Run the digest and pruning in Huey's consumer when Huey is installed.
    The queue they run on, or None without Huey. Registering twice does
    nothing.
    """
    global _registered

    if _registered is not None:
        return _registered

    from ..contrib.backups.huey import close_db, get_huey

    huey = huey if huey is not None else get_huey()

    if huey is None:
        return None

    from huey import crontab

    for func, schedule in (
        (notification_digest, crontab(minute=DIGEST_MINUTE)),
        (
            notification_pruning,
            crontab(hour=PRUNING_HOUR, minute=PRUNING_MINUTE),
        ),
    ):
        locked = huey.lock_task(f"{func.__module__}.{func.__name__}")(func)
        huey.periodic_task(schedule, name=func.__name__)(close_db(locked))

    _registered = huey
    return huey


# The last runs, for the system status page


def _cache_key(task: str) -> str:
    return f"content_studio:notifications:last_run:{task}"


def record_run(task: str, error: Optional[BaseException] = None) -> None:
    """Remember a run of a task (now), and how it ended."""
    from django.core.cache import cache

    message = f"{type(error).__name__}: {error}" if error is not None else ""

    try:
        cache.set(_cache_key(task), (timezone.now(), message), None)
    except Exception:  # pragma: no cover -- a cache that is down
        logger.warning("Could not store the last run of %s.", task)


def get_last_run(task: str):
    """The last run of a task as a status Run, or None."""
    from django.core.cache import cache

    from ..contrib.status import Run

    try:
        value = cache.get(_cache_key(task))
    except Exception:  # pragma: no cover
        return None

    if not value:
        return None

    at, message = value
    return Run(at=at, ok=not message, message=message)


def register_status(huey) -> None:
    """The two tasks on the system status page (harmless without the app)."""
    from functools import partial

    from ..contrib.status import register_recurring_task

    utc = bool(getattr(huey, "utc", True))

    register_recurring_task(
        DIGEST_TASK,
        _("Notification digest"),
        schedule=_("Every hour at :10"),
        get_last_run=partial(get_last_run, DIGEST_TASK),
        group=_("Content Studio"),
    )
    register_recurring_task(
        PRUNING_TASK,
        _("Notification pruning"),
        schedule=_("Daily at 04:30 UTC") if utc else _("Daily at 04:30"),
        get_last_run=partial(get_last_run, PRUNING_TASK),
        group=_("Content Studio"),
    )
