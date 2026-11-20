"""
Scheduled backups with Huey: when huey.contrib.djhuey is installed, a
periodic task runs the backups on BACKUP_SCHEDULE in Huey's consumer.
"""

import functools

from django.apps import apps
from django.db import close_old_connections

HUEY_APP = "huey.contrib.djhuey"

# The periodic task, once registered.
_periodic = None


def get_huey():
    """djhuey's HUEY when Huey is installed, else None."""
    if not apps.is_installed(HUEY_APP):
        return None

    from huey.contrib.djhuey import HUEY

    return HUEY


def close_db(func):
    """Fresh database connections around a run, as djhuey's db tasks."""

    @functools.wraps(func)
    def inner(*args, **kwargs):
        close_old_connections()
        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()

    return inner


def register_periodic_task(huey=None):
    """
    Run the backups on BACKUP_SCHEDULE in Huey's consumer: a periodic
    task named content_studio.contrib.backups.tasks.scheduled_backup.
    """
    global _periodic

    if _periodic is not None:
        return _periodic

    huey = huey if huey is not None else get_huey()

    if huey is None:
        return None

    from .schedule import get_schedule

    schedule = get_schedule()

    if schedule is None:
        return None

    from huey import crontab

    from .tasks import scheduled_backup

    _periodic = huey.periodic_task(crontab(**schedule.huey_crontab_kwargs()))(
        close_db(scheduled_backup)
    )
    return _periodic
