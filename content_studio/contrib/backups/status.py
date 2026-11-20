"""
The backups on the system status page: the "Database backups" service
and the recurring backup, when content_studio.contrib.status is
installed (registering is harmless otherwise).
"""

import datetime

from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext as _
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy

from ..status import Run, degraded, down, ok, unknown
from ..status import register_recurring_task, register_service, register_task

SERVICE_KEY = "content_studio.backups"
RECURRING_KEY = "content_studio.contrib.backups.tasks.scheduled_backup"
GROUP = gettext_lazy("Content Studio")
LABEL = gettext_lazy("Back up the database")

# How long past its scheduled time a backup may be before it is overdue.
GRACE = datetime.timedelta(hours=1)


def check_backups():
    from ...settings import cs_settings
    from .backup import BackupError, get_databases, get_storage
    from .models import Backup
    from .schedule import get_schedule, next_run

    try:
        storage = get_storage()
    except BackupError as exc:
        return down(_("No backup storage"), str(exc))

    if cs_settings.BACKUP_STORAGE != "default":
        # The media storage has its own row; another storage is checked here.
        storage.exists("content-studio-backups-check")

    aliases = get_databases()

    if not aliases:
        return unknown(_("No databases to back up"))

    now = timezone.now()
    schedule = get_schedule()
    worst = None
    latest_done = None

    for alias in aliases:
        finished = (
            Backup.objects.filter(
                database=alias, status__in=[Backup.DONE, Backup.FAILED]
            )
            .order_by("-created_at", "-id")
            .first()
        )
        done = (
            Backup.objects.filter(database=alias, status=Backup.DONE)
            .order_by("-created_at", "-id")
            .first()
        )

        if done is not None and (
            latest_done is None or done.created_at > latest_done.created_at
        ):
            latest_done = done

        if finished is not None and finished.status == Backup.FAILED:
            message = _("The last backup of %(database)s failed: %(error)s") % {
                "database": alias,
                "error": finished.error,
            }
            worst = ("down", message)
            continue

        if done is None:
            if worst is None:
                worst = ("degraded", _("No backup has been made yet."))
            continue

        if schedule is not None:
            due = next_run(after=done.started_at or done.created_at)

            if due is not None and due + GRACE < now and worst is None:
                worst = (
                    "degraded",
                    _("The backup of %(database)s is overdue by %(when)s.")
                    % {"database": alias, "when": timesince(due, now)},
                )

    if latest_done is None:
        detail = _("No backups yet")
    else:
        made = latest_done.finished_at or latest_done.created_at
        size = filesizeformat(latest_done.size or 0)
        detail = (
            _("Last backup just now · %(size)s") % {"size": size}
            if now - made < datetime.timedelta(minutes=1)
            else _("Last backup %(when)s ago · %(size)s")
            % {"when": timesince(made, now), "size": size}
        )

    if worst is not None and worst[0] == "down":
        return down(detail, worst[1])

    if schedule is None:
        # Nothing is due: made on demand, or by a schedule of your own.
        return unknown(detail, _("Backups are not scheduled."))

    if worst is not None:
        return degraded(detail, worst[1])

    return ok(detail)


def get_last_run():
    from .models import Backup

    backup = (
        Backup.objects.filter(status__in=[Backup.DONE, Backup.FAILED])
        .order_by("-created_at", "-id")
        .first()
    )

    if backup is None:
        return None

    return Run(
        at=backup.finished_at or backup.created_at,
        ok=backup.status == Backup.DONE,
        message=backup.error,
    )


def get_next_run():
    from .schedule import next_run

    return next_run()


def register():
    from .schedule import get_schedule

    register_service(
        SERVICE_KEY,
        gettext_lazy("Database backups"),
        check_backups,
        icon="ph-bold ph-archive",
        group=GROUP,
        url="backups",
    )

    schedule = get_schedule()

    if schedule is not None:
        register_recurring_task(
            RECURRING_KEY,
            LABEL,
            # In words, in the language of the request.
            schedule=lazy(schedule.describe, str)(),
            get_last_run=get_last_run,
            get_next_run=get_next_run,
            group=GROUP,
        )

    register_task("content_studio.contrib.backups.tasks.backup_database", LABEL)
    register_task(RECURRING_KEY, LABEL)
