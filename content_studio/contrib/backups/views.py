import logging
import posixpath

from django.http import FileResponse
from django.utils.translation import gettext as _
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ...permissions import IsActiveStaff
from ...settings import cs_settings
from .backup import BackupError, get_databases, get_storage, mark_stale
from .models import Backup

logger = logging.getLogger("content_studio.backups")

# Backups the page lists.
LIMIT = 100


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


class BackupViewSet(ViewSet):
    """The Backups page: the list, Back up now and the downloads."""

    # Explicit, so the project's DEFAULT_PERMISSION_CLASSES never decide.
    permission_classes = [IsActiveStaff, HasBackupPermission]
    renderer_classes = [JSONRenderer]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        admin_site = cs_settings.ADMIN_SITE
        self.authentication_classes = [
            admin_site.token_backend.active_backend.authentication_class
        ]

    def list(self, request):
        from .schedule import get_schedule, next_run

        mark_stale()
        schedule = get_schedule()
        backups = Backup.objects.select_related("created_by")[:LIMIT]

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


def set_up_router():
    from ...router import content_studio_router

    content_studio_router.register(
        "api/backups", BackupViewSet, basename="content_studio_backups"
    )
