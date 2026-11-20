import logging
import os
import posixpath
import shutil
import tempfile

from django.db import connections
from django.http import FileResponse
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext as _
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ...parsers import ObjectJSONParser
from ...permissions import IsActiveStaff
from ...settings import cs_settings
from .backup import BackupError, get_databases, get_storage, mark_stale
from .fixtures import SUFFIXES, fixture_suffix
from .models import Backup, Restore

logger = logging.getLogger("content_studio.backups")

# Backups the page lists.
LIMIT = 100

# Restores the page lists.
RESTORE_LIMIT = 10


class HasBackupPermission(BasePermission):
    """Whoever the admin site's has_backup_permission() lets in."""

    def has_permission(self, request, view):
        return bool(cs_settings.ADMIN_SITE.has_backup_permission(request))


def iso(value):
    return None if value is None else value.isoformat()


def serialize(backup: Backup) -> dict:
    return {
        "id": backup.pk,
        "database": backup.database,
        "status": backup.status,
        "trigger": backup.trigger,
        "file": backup.file,
        "name": posixpath.basename(backup.file) if backup.file else "",
        "size": backup.size,
        "error": backup.error or None,
        "created_by": str(backup.created_by) if backup.created_by_id else None,
        "created_at": iso(backup.created_at),
        "started_at": iso(backup.started_at),
        "finished_at": iso(backup.finished_at),
        "duration": backup.duration,
    }


def serialize_restore(record: Restore) -> dict:
    return {
        "id": record.pk,
        "database": record.database,
        "status": record.status,
        "source": record.source,
        "backup": record.backup_id,
        "name": record.name,
        "size": record.size,
        "rows": record.rows,
        "error": record.error or None,
        "safety_backup": (
            posixpath.basename(record.safety_backup.file)
            if record.safety_backup_id and record.safety_backup.file
            else None
        ),
        "created_by": str(record.created_by) if record.created_by_id else None,
        "created_at": iso(record.created_at),
        "started_at": iso(record.started_at),
        "finished_at": iso(record.finished_at),
        "duration": record.duration,
    }


def restore_info(request) -> dict:
    """Whether the user may restore here, and what the dialog needs."""
    from .backup import database_name

    return {
        "enabled": bool(cs_settings.ADMIN_SITE.has_restore_permission(request)),
        "databases": [
            {"alias": alias, "name": database_name(alias)}
            for alias in get_databases()
            if alias in connections.databases
        ],
        "max_upload_size": cs_settings.BACKUP_UPLOAD_MAX_SIZE,
        # Accounts without a password (single sign-on) are not asked for one.
        "password_required": request.user.has_usable_password(),
        "suffixes": list(SUFFIXES),
    }


class BackupViewSet(ViewSet):
    """The Backups page: the list, Back up now and the downloads."""

    # Explicit, so the project's DEFAULT_PERMISSION_CLASSES never decide.
    permission_classes = [IsActiveStaff, HasBackupPermission]
    renderer_classes = [JSONRenderer]
    parser_classes = [ObjectJSONParser, MultiPartParser]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        admin_site = cs_settings.ADMIN_SITE
        self.authentication_classes = [
            admin_site.token_backend.active_backend.authentication_class
        ]

    def list(self, request):
        from .backup import clean_uploads, mark_stale_restores
        from .schedule import get_schedule, next_run

        mark_stale()
        mark_stale_restores()
        clean_uploads()
        schedule = get_schedule()
        backups = Backup.objects.select_related("created_by")[:LIMIT]
        restores = Restore.objects.exclude(status=Restore.PENDING).select_related(
            "created_by", "safety_backup"
        )[:RESTORE_LIMIT]

        try:
            storage = get_storage()
            storage_name = type(storage).__name__
        except BackupError:
            storage_name = None

        return Response(
            {
                "backups": [serialize(backup) for backup in backups],
                "schedule": schedule.describe() if schedule else None,
                "next_run_at": iso(next_run()),
                "keep": cs_settings.BACKUP_KEEP,
                "databases": get_databases(),
                "storage": storage_name,
                "folder": cs_settings.BACKUP_FOLDER,
                "restores": [serialize_restore(record) for record in restores],
                "restore": restore_info(request),
            }
        )

    def create(self, request):
        """Back up now: every database in BACKUP_DATABASES."""
        from .tasks import enqueue_backups

        queued = enqueue_backups(request.user)

        if not queued:
            return Response(
                {"detail": _("A backup is already queued or running.")},
                status=http_status.HTTP_409_CONFLICT,
            )

        return Response(
            {"backups": [serialize(backup) for backup in queued]},
            status=http_status.HTTP_202_ACCEPTED,
        )

    @action(methods=["get"], detail=True, url_path="download")
    def download(self, request, pk=None):
        backup = Backup.objects.filter(pk=pk, status=Backup.DONE).first()

        if backup is None or not backup.file:
            raise NotFound(_("There is no such backup."))

        try:
            storage = get_storage()
            file = storage.open(backup.file, "rb")
        except (BackupError, FileNotFoundError, OSError):
            raise NotFound(_("The backup's file is no longer in the storage."))

        logger.info("%s downloaded the backup %s.", request.user, backup.file)

        return FileResponse(
            file,
            as_attachment=True,
            filename=posixpath.basename(backup.file),
            content_type="application/gzip",
        )

    # Restoring

    def check_restore_permission(self, request):
        if not cs_settings.ADMIN_SITE.has_restore_permission(request):
            raise PermissionDenied(_("You may not restore backups here."))

    @action(methods=["get"], detail=True, url_path="inspect")
    def inspect(self, request, pk=None):
        """What restoring a listed backup would load."""
        from .backup import RestoreError, preview_backup

        self.check_restore_permission(request)
        backup = Backup.objects.filter(pk=pk, status=Backup.DONE).first()

        if backup is None or not backup.file:
            raise NotFound(_("There is no such backup."))

        try:
            preview = preview_backup(backup)
        except (RestoreError, BackupError, OSError) as exc:
            return Response(
                {"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST
            )

        return Response({"preview": preview})

    @action(methods=["post"], detail=False, url_path="uploads")
    def upload(self, request):
        """
        Upload a file to restore: it is read and checked, saved in the
        backup storage and returned with what it holds. It waits there
        until it is restored, cancelled or a day has passed.
        """
        from .backup import (
            RestoreError,
            clean_uploads,
            preview_file,
            upload_name,
        )

        self.check_restore_permission(request)
        clean_uploads()
        file = request.FILES.get("file")

        if file is None:
            return Response(
                {"file": [_("Choose a file to restore.")]},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        suffix = fixture_suffix(file.name)

        if suffix is None:
            return Response(
                {
                    "file": [
                        _("Only JSON fixtures can be restored: %(suffixes)s.")
                        % {"suffixes": ", ".join(SUFFIXES)}
                    ]
                },
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        max_size = cs_settings.BACKUP_UPLOAD_MAX_SIZE

        if max_size is not None and file.size > max_size:
            return Response(
                {
                    "file": [
                        _("The file is larger than %(size)s.")
                        % {"size": filesizeformat(max_size)}
                    ]
                },
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        databases = get_databases()
        alias = request.data.get("database") or (databases[0] if databases else None)

        if alias not in databases or alias not in connections.databases:
            return Response(
                {"database": [_("Choose a database that is backed up.")]},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        folder = tempfile.mkdtemp(prefix="content-studio-upload-")

        try:
            path = os.path.join(folder, "upload" + suffix)

            with open(path, "wb") as target:
                for chunk in file.chunks():
                    target.write(chunk)

            try:
                preview = preview_file(path, alias)
            except RestoreError as exc:
                return Response(
                    {"file": [str(exc)]}, status=http_status.HTTP_400_BAD_REQUEST
                )

            try:
                storage = get_storage()
                with open(path, "rb") as source:
                    name = storage.save(upload_name(file.name), source)
            except (BackupError, OSError) as exc:
                logger.exception("Could not save the upload %s.", file.name)
                return Response(
                    {"detail": str(exc)},
                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

        record = Restore.objects.create(
            database=alias,
            status=Restore.PENDING,
            source=Restore.UPLOAD,
            file=name,
            name=posixpath.basename(file.name),
            size=file.size,
            preview=preview,
            created_by=request.user,
        )
        logger.info("%s uploaded %s to restore.", request.user, record.name)

        return Response(
            {"upload": serialize_restore(record), "preview": preview},
            status=http_status.HTTP_201_CREATED,
        )

    @action(
        methods=["delete"],
        detail=False,
        url_path=r"uploads/(?P<upload_id>[0-9]+)",
    )
    def cancel_upload(self, request, upload_id=None):
        """Delete an upload that is not restored."""
        from .backup import delete_upload

        self.check_restore_permission(request)
        record = Restore.objects.filter(
            pk=upload_id, status=Restore.PENDING, source=Restore.UPLOAD
        ).first()

        if record is None:
            raise NotFound(_("There is no such upload."))

        delete_upload(record)
        record.delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT)

    @action(methods=["post"], detail=False, url_path="restore")
    def restore(self, request):
        """
        Start a restore of a listed backup ("backup": id) or an upload
        ("upload": id). The database's name ("confirm") and the user's
        password ("password") must be given; "safety_backup" (true) backs
        up the current data first, "ignore_migrations" restores although
        the migrations differ or cannot be checked.
        """
        from .backup import (
            RestoreError,
            database_name,
            is_restoring,
            is_running,
            preview_backup,
        )
        from .tasks import enqueue_restore

        self.check_restore_permission(request)
        data = request.data
        backup_id = data.get("backup")
        upload_id = data.get("upload")
        record = None

        if upload_id:
            record = Restore.objects.filter(
                pk=upload_id, status=Restore.PENDING, source=Restore.UPLOAD
            ).first()

            if record is None:
                raise NotFound(_("The upload is gone. Upload the file again."))

            alias = record.database
            preview = record.preview
        elif backup_id:
            backup = Backup.objects.filter(pk=backup_id, status=Backup.DONE).first()

            if backup is None or not backup.file:
                raise NotFound(_("There is no such backup."))

            alias = backup.database

            try:
                preview = preview_backup(backup)
            except (RestoreError, BackupError, OSError) as exc:
                return Response(
                    {"detail": str(exc)}, status=http_status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {"detail": _("Choose a backup or upload a file to restore.")},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if alias not in connections.databases:
            return Response(
                {
                    "detail": _("The database %(alias)s is not configured.")
                    % {"alias": alias}
                },
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        errors = {}

        if str(data.get("confirm") or "").strip() != database_name(alias):
            errors["confirm"] = [
                _("Type %(name)s to confirm.") % {"name": database_name(alias)}
            ]

        user = request.user

        if user.has_usable_password() and not user.check_password(
            str(data.get("password") or "")
        ):
            errors["password"] = [_("Your password is not correct.")]

        ignore_migrations = data.get("ignore_migrations") is True
        migrations = preview.get("migrations") or {}

        if preview.get("unknown_models"):
            errors["detail"] = _(
                "The file holds models that are not installed: %(models)s."
            ) % {"models": ", ".join(preview["unknown_models"][:10])}
        elif not migrations.get("match") and not ignore_migrations:
            errors["ignore_migrations"] = [
                _(
                    "The migrations differ or cannot be checked. Confirm to restore anyway."
                )
            ]

        if errors:
            return Response(errors, status=http_status.HTTP_400_BAD_REQUEST)

        if is_restoring(alias) or is_running(alias):
            return Response(
                {"detail": _("A backup or restore of this database is running.")},
                status=http_status.HTTP_409_CONFLICT,
            )

        options = {
            "status": Restore.QUEUED,
            "make_safety_backup": data.get("safety_backup") is not False,
            "ignore_migrations": ignore_migrations,
            "created_by": user,
        }

        if record is None:
            record = Restore.objects.create(
                database=alias,
                source=Restore.BACKUP,
                backup=backup,
                file=backup.file,
                name=posixpath.basename(backup.file),
                size=backup.size,
                preview=preview,
                **options,
            )
        else:
            for key, value in options.items():
                setattr(record, key, value)
            record.save()

        logger.warning("%s started a restore of %s into %r.", user, record.name, alias)
        enqueue_restore(record)

        return Response(
            {"restore": serialize_restore(record)},
            status=http_status.HTTP_202_ACCEPTED,
        )


def set_up_router():
    from ...router import content_studio_router

    content_studio_router.register(
        "api/backups", BackupViewSet, basename="content_studio_backups"
    )
