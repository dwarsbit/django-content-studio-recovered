"""
Making, keeping and restoring backups.

A backup is a Django fixture: the JSON dumpdata writes, gzipped, with
natural foreign keys, so loaddata reads it back on any database engine.
Beside it in the storage lies its manifest (`<name>.manifest.json`): the
versions, the database engine, the applied migrations and the rows per
model, which a restore checks before it loads anything.
"""

import datetime
import json
import logging
import os
import posixpath
import secrets
import shutil
import tempfile
from typing import Iterable, Optional

import django
from django.apps import apps
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import InvalidStorageError, storages
from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections, router, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from ...settings import cs_settings
from .models import Backup

logger = logging.getLogger("content_studio.backups")

FORMAT = 1
EXTENSION = ".json.gz"
MANIFEST_EXTENSION = ".manifest.json"

# Left out of every backup: rebuilt by migrate (content types,
# permissions), short-lived (sessions) or about the backups themselves.
DEFAULT_EXCLUDE = [
    "contenttypes",
    "auth.permission",
    "sessions",
    "content_studio_backups",
]

# Left out when their app is installed: password reset codes are
# short-lived, and a backup should not hold codes that are still valid.
DEFAULT_EXCLUDE_IF_INSTALLED = {
    "content_studio.contrib.password_reset": "password_reset.PasswordResetCode",
}

# A backup still queued or running after this long did not finish.
STALE_AFTER = datetime.timedelta(hours=6)


class BackupError(Exception):
    pass


class BackupRunning(BackupError):
    pass


class RestoreError(Exception):
    pass


# Storage


def get_storage():
    """The storage backups are saved in: BACKUP_STORAGE in STORAGES."""
    try:
        return storages[cs_settings.BACKUP_STORAGE]
    except InvalidStorageError as exc:
        raise BackupError(str(exc)) from exc


def get_databases() -> list[str]:
    return list(cs_settings.BACKUP_DATABASES or [])


def backup_name(alias: str, moment: datetime.datetime) -> str:
    """
    The backup's name in the storage: the UTC time it started, so names
    sort by age, and a random token, so a name cannot be guessed from the
    schedule even where the storage serves its files.
    """
    stamp = moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    token = secrets.token_hex(16)
    return posixpath.join(
        cs_settings.BACKUP_FOLDER, alias, f"{stamp}-{token}{EXTENSION}"
    )


def manifest_name(name: str) -> str:
    base = name[: -len(EXTENSION)] if name.endswith(EXTENSION) else name
    return base + MANIFEST_EXTENSION


# What a backup leaves out and holds


def get_excludes() -> list[str]:
    """
    The app labels and models left out: the defaults and BACKUP_EXCLUDE,
    without those not installed (dumpdata refuses unknown ones).
    """
    excludes = []
    defaults = [
        *DEFAULT_EXCLUDE,
        *(
            label
            for app, label in DEFAULT_EXCLUDE_IF_INSTALLED.items()
            if apps.is_installed(app)
        ),
    ]

    for label in [*defaults, *(cs_settings.BACKUP_EXCLUDE or [])]:
        app_label, _dot, model_name = label.partition(".")

        try:
            config = apps.get_app_config(app_label)
            if model_name:
                config.get_model(model_name)
        except LookupError:
            continue

        if label not in excludes:
            excludes.append(label)

    return excludes


def is_excluded(model, excludes: Iterable[str]) -> bool:
    excludes = set(excludes)
    return (
        model._meta.app_label in excludes
        or model._meta.label in excludes
        or model._meta.label_lower in excludes
    )


def get_models(alias: str, excludes: list[str]) -> list:
    """The models dumpdata writes for a database."""
    return [
        model
        for model in apps.get_models()
        if not model._meta.proxy
        and model._meta.managed
        and router.allow_migrate_model(alias, model)
        and not is_excluded(model, excludes)
    ]


def get_applied_migrations(alias: str) -> dict[str, list[str]]:
    recorder = MigrationRecorder(connections[alias])

    if not recorder.has_table():
        return {}

    applied: dict[str, list[str]] = {}

    for app_label, name in sorted(recorder.applied_migrations()):
        applied.setdefault(app_label, []).append(name)

    return applied


def build_manifest(alias: str, excludes: list[str]) -> dict:
    from content_studio import __version__

    connection = connections[alias]
    counts = {}

    for model in get_models(alias, excludes):
        try:
            counts[model._meta.label] = model._default_manager.using(alias).count()
        except Exception:
            # A table that is not there: dumpdata reports it.
            counts[model._meta.label] = None

    return {
        "format": FORMAT,
        "created_at": timezone.now().isoformat(),
        "database": alias,
        "engine": connection.vendor,
        "content_studio": __version__,
        "django": django.get_version(),
        "excluded": excludes,
        "migrations": get_applied_migrations(alias),
        "counts": counts,
    }


# Records


def records_database() -> str:
    return router.db_for_write(Backup)


def mark_stale(alias: Optional[str] = None) -> None:
    """Backups queued or running for STALE_AFTER did not finish."""
    queryset = Backup.objects.using(records_database()).filter(
        status__in=[Backup.QUEUED, Backup.RUNNING],
        created_at__lt=timezone.now() - STALE_AFTER,
    )

    if alias is not None:
        queryset = queryset.filter(database=alias)

    queryset.update(
        status=Backup.FAILED,
        error="The backup did not finish.",
        finished_at=timezone.now(),
    )


def is_running(alias: str, exclude_pk=None) -> bool:
    mark_stale(alias)
    queryset = Backup.objects.using(records_database()).filter(
        database=alias, status__in=[Backup.QUEUED, Backup.RUNNING]
    )

    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)

    return queryset.exists()


def queue_backup(alias: str, trigger: str, user=None) -> Backup:
    """A record for a backup that a task will make."""
    if alias not in connections.databases:
        raise BackupError(f"There is no database {alias!r}.")

    if is_running(alias):
        raise BackupRunning(f"A backup of {alias!r} is already queued or running.")

    return Backup.objects.using(records_database()).create(
        database=alias,
        trigger=trigger,
        status=Backup.QUEUED,
        created_by=user if user is not None and user.pk else None,
    )


# Making a backup


def dump(alias: str, path: str, excludes: list[str]) -> None:
    """Write the database's fixture to path (gzipped by its extension)."""
    call_command(
        "dumpdata",
        database=alias,
        exclude=excludes,
        natural_foreign=True,
        output=path,
        verbosity=0,
    )


def make_backup(
    alias: str = "default",
    trigger: str = Backup.SCHEDULED,
    backup: Optional[Backup] = None,
    user=None,
) -> Backup:
    """
    Back up one database: dump it, save the file and its manifest in the
    backup storage and prune the old ones. Returns the record; a failure
    is recorded on it (status FAILED, error) and raised as BackupError.
    """
    using = records_database()

    if backup is None:
        backup = queue_backup(alias, trigger, user)
    else:
        backup.refresh_from_db(using=using)
        alias = backup.database

        if backup.status not in (Backup.QUEUED, Backup.RUNNING):
            return backup

    backup.status = Backup.RUNNING
    backup.started_at = timezone.now()
    backup.save(using=using, update_fields=["status", "started_at"])

    folder = tempfile.mkdtemp(prefix="content-studio-backup-")
    storage = None
    name = None

    try:
        storage = get_storage()
        excludes = get_excludes()
        manifest = build_manifest(alias, excludes)
        path = os.path.join(folder, "backup" + EXTENSION)

        dump(alias, path, excludes)

        with open(path, "rb") as file:
            name = storage.save(backup_name(alias, backup.started_at), File(file))

        storage.save(
            manifest_name(name),
            ContentFile(
                json.dumps(manifest, cls=DjangoJSONEncoder, indent=2).encode("utf-8")
            ),
        )

        backup.file = name
        backup.size = os.path.getsize(path)
        backup.manifest = manifest
        backup.status = Backup.DONE
        backup.error = ""
    except Exception as exc:
        logger.exception("The backup of database %r failed.", alias)

        if storage is not None and name:
            # Half saved: nothing of it is kept.
            delete_files(storage, name)

        backup.status = Backup.FAILED
        backup.error = f"{type(exc).__name__}: {exc}".rstrip(": ")
        backup.file = ""
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        backup.finished_at = timezone.now()
        backup.save(using=using)

    if backup.status == Backup.FAILED:
        raise BackupError(backup.error)

    prune(alias)
    return backup


def make_backups(trigger: str = Backup.SCHEDULED) -> list[Backup]:
    """Back up every database in BACKUP_DATABASES; failures are logged."""
    made = []

    for alias in get_databases():
        try:
            made.append(make_backup(alias, trigger))
        except BackupError:
            # Recorded on the backup and logged.
            pass

    return made


# Keeping backups


def delete_files(storage, name: str) -> None:
    for path in (name, manifest_name(name)):
        try:
            if storage.exists(path):
                storage.delete(path)
        except Exception:
            logger.warning("Could not delete %s.", path, exc_info=True)


def prune(alias: str) -> int:
    """
    Keep the newest BACKUP_KEEP backups of a database: older ones are
    deleted, files and records, and so are failed runs older than the
    oldest backup kept. Returns how many records were deleted.
    """
    keep = cs_settings.BACKUP_KEEP

    if not keep:
        return 0

    using = records_database()
    done = Backup.objects.using(using).filter(database=alias, status=Backup.DONE)
    kept = list(done.order_by("-created_at", "-id")[:keep])

    if len(kept) < keep:
        return 0

    oldest = kept[-1]
    old = (
        Backup.objects.using(using)
        .filter(database=alias, status__in=[Backup.DONE, Backup.FAILED])
        .exclude(pk__in=[backup.pk for backup in kept])
        .filter(created_at__lte=oldest.created_at)
    )
    storage = get_storage()
    deleted = 0

    for backup in old:
        if backup.file:
            delete_files(storage, backup.file)
        backup.delete(using=using)
        deleted += 1

    return deleted


# Restoring a backup


def fetch(name: str, folder: str) -> tuple[str, Optional[dict]]:
    """
    The backup as a local file, with its manifest: name is a file on
    disk, or a name in the backup storage.
    """
    path = os.path.join(folder, "restore" + EXTENSION)

    if os.path.isfile(name):
        shutil.copyfile(name, path)
        manifest_path = manifest_name(name)
        manifest = None

        if os.path.isfile(manifest_path):
            with open(manifest_path, encoding="utf-8") as file:
                manifest = json.load(file)

        return path, manifest

    storage = get_storage()

    if not storage.exists(name):
        raise RestoreError(f"There is no backup {name!r}.")

    with storage.open(name, "rb") as source, open(path, "wb") as target:
        shutil.copyfileobj(source, target)

    manifest = None

    if storage.exists(manifest_name(name)):
        with storage.open(manifest_name(name), "rb") as file:
            manifest = json.loads(file.read().decode("utf-8"))
    else:
        record = (
            Backup.objects.using(records_database())
            .filter(file=name)
            .exclude(manifest={})
            .first()
        )
        manifest = record.manifest if record else None

    return path, manifest


def migration_differences(alias: str, manifest: dict) -> tuple[list, list]:
    """Migrations the backup has that the database lacks, and the reverse."""
    current = {
        (app, name)
        for app, names in get_applied_migrations(alias).items()
        for name in names
    }
    backed_up = {
        (app, name)
        for app, names in (manifest.get("migrations") or {}).items()
        for name in names
    }

    return sorted(backed_up - current), sorted(current - backed_up)


def latest_backup(alias: str) -> Optional[Backup]:
    return (
        Backup.objects.using(records_database())
        .filter(database=alias, status=Backup.DONE)
        .exclude(file="")
        .order_by("-created_at", "-id")
        .first()
    )


def keep_records(records: list[Backup], using: str) -> None:
    """Put the backup records back after a restore emptied their table."""
    from django.contrib.auth import get_user_model

    user_ids = {record.created_by_id for record in records if record.created_by_id}
    known = set(
        get_user_model()
        ._default_manager.using(using)
        .filter(pk__in=user_ids)
        .values_list("pk", flat=True)
    )

    for record in records:
        if record.created_by_id not in known:
            record.created_by_id = None

    Backup.objects.using(using).bulk_create(records)


def restore(name: str, alias: str = "default", ignore_migrations: bool = False):
    """
    Replace the database's contents with a backup: every table is
    emptied and the backup loaded, in one transaction. The backup
    records themselves are kept as they are.
    """
    if alias not in connections.databases:
        raise RestoreError(f"There is no database {alias!r}.")

    folder = tempfile.mkdtemp(prefix="content-studio-restore-")

    try:
        path, manifest = fetch(name, folder)

        if manifest is None:
            if not ignore_migrations:
                raise RestoreError(
                    "The backup has no manifest, so its migrations cannot be "
                    "checked. Pass --ignore-migrations to restore it anyway."
                )
        elif manifest.get("format", FORMAT) > FORMAT:
            raise RestoreError("The backup was made by a newer Content Studio.")
        elif not ignore_migrations:
            missing, extra = migration_differences(alias, manifest)

            if missing or extra:
                lines = [
                    "The backup's migrations differ from the database's.",
                    *(f"  Only in the backup: {a}.{n}" for a, n in missing[:10]),
                    *(f"  Only in the database: {a}.{n}" for a, n in extra[:10]),
                    "Migrate the database to the backup's state first, or pass "
                    "--ignore-migrations.",
                ]
                raise RestoreError("\n".join(lines))

        using = records_database()
        records = list(Backup.objects.using(using).all()) if using == alias else None

        with transaction.atomic(using=alias):
            call_command("flush", database=alias, interactive=False, verbosity=0)
            call_command("loaddata", path, database=alias, verbosity=0)

            if records:
                keep_records(records, using)
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    if apps.is_installed("django.contrib.contenttypes"):
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()

    return manifest
