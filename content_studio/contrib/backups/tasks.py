"""
The backup tasks.

backup_database is a Django task: "Back up now" enqueues it, and the
project's TASKS backend runs it (Django's ImmediateBackend runs it in
place, after the request's transaction commits). Django 5.2 has no
django.tasks; there the django-tasks backport is used when installed,
and otherwise the backup runs in place.

scheduled_backup is what Huey's periodic task runs on BACKUP_SCHEDULE
(see huey.py), and what content_studio_backup runs from cron.

restore_database carries out a restore started on the Backups page, the
same way: on the task backend when there is one, in place otherwise.
"""

import logging

from django.db import transaction

try:
    from django.tasks import task
except ImportError:  # Django < 6.0
    try:
        from django_tasks import task
    except ImportError:
        task = None

logger = logging.getLogger("content_studio.backups")


def run_backup(backup_id: int) -> None:
    """Make the queued backup with this id."""
    from .backup import BackupError, make_backup, records_database
    from .models import Backup

    backup = Backup.objects.using(records_database()).filter(pk=backup_id).first()

    if backup is None:
        return

    try:
        make_backup(backup=backup)
    except BackupError:
        # Recorded on the backup and logged.
        pass


def scheduled_backup():
    """Back up the database (Content Studio's scheduled backup)."""
    from .backup import clean_uploads, make_backups
    from .models import Backup

    make_backups(Backup.SCHEDULED)
    clean_uploads()


class _SynchronousTask:
    """The enqueue interface of a task, running the function in place."""

    def __init__(self, func):
        self.func = func

    def enqueue(self, *args, **kwargs):
        return self.func(*args, **kwargs)


def backup_database(backup_id: int) -> None:
    run_backup(backup_id)


backup_database_task = (
    task(backup_database) if task is not None else _SynchronousTask(backup_database)
)


def enqueue_backups(user=None) -> list:
    """
    Queue a backup of every database in BACKUP_DATABASES ("Back up now")
    and enqueue their task once the request's transaction commits.
    Databases with a backup already queued or running are left out.
    """
    from .backup import BackupRunning, get_databases, queue_backup
    from .models import Backup

    queued = []

    for alias in get_databases():
        try:
            queued.append(queue_backup(alias, Backup.MANUAL, user))
        except BackupRunning:
            continue

    def enqueue():
        for backup in queued:
            try:
                backup_database_task.enqueue(backup.pk)
            except Exception as exc:
                logger.exception("Could not enqueue the backup %s.", backup.pk)
                Backup.objects.filter(pk=backup.pk).update(
                    status=Backup.FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                )

    transaction.on_commit(enqueue)
    return queued


def restore_database(restore_id: int) -> None:
    """Carry out the queued restore with this id."""
    from .backup import records_database, run_restore
    from .models import Restore

    record = Restore.objects.using(records_database()).filter(pk=restore_id).first()

    if record is not None:
        run_restore(record)


restore_database_task = (
    task(restore_database) if task is not None else _SynchronousTask(restore_database)
)


def enqueue_restore(record) -> None:
    """Enqueue a queued restore's task once the request's transaction commits."""
    from .models import Restore

    def enqueue():
        try:
            restore_database_task.enqueue(record.pk)
        except Exception as exc:
            logger.exception("Could not enqueue the restore %s.", record.pk)
            Restore.objects.filter(pk=record.pk).update(
                status=Restore.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

    transaction.on_commit(enqueue)
