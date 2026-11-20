from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Backup(models.Model):
    """
    One backup of one database: when it ran, how it went and where its
    file is in the backup storage.
    """

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

    STATUS_CHOICES = [
        (QUEUED, _("Queued")),
        (RUNNING, _("Running")),
        (DONE, _("Done")),
        (FAILED, _("Failed")),
    ]

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    COMMAND = "command"
    BEFORE_RESTORE = "before_restore"

    TRIGGER_CHOICES = [
        (SCHEDULED, _("Scheduled")),
        (MANUAL, _("Back up now")),
        (COMMAND, _("Command")),
        (BEFORE_RESTORE, _("Before restore")),
    ]

    database = models.CharField(_("database"), max_length=100, default="default")
    status = models.CharField(
        _("status"), max_length=20, choices=STATUS_CHOICES, default=QUEUED
    )
    trigger = models.CharField(
        _("trigger"), max_length=20, choices=TRIGGER_CHOICES, default=SCHEDULED
    )
    # The file's name in the backup storage.
    file = models.CharField(_("file"), max_length=500, blank=True)
    # Bytes.
    size = models.BigIntegerField(_("size"), null=True, blank=True)
    # What the backup holds: versions, migrations and rows per model.
    manifest = models.JSONField(_("manifest"), default=dict, blank=True)
    error = models.TextField(_("error"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        verbose_name = _("backup")
        verbose_name_plural = _("backups")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["database", "status", "-created_at"])]

    def __str__(self):
        return self.file or f"{self.database} ({self.get_status_display()})"

    @property
    def duration(self):
        """Seconds the backup took, once it finished."""
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds())
        return None


class Restore(models.Model):
    """
    One restore of a database: a listed backup or an uploaded file put
    in place of its data. An upload waits as PENDING until it is
    restored or cleaned up. The records survive the restore itself.
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

    STATUS_CHOICES = [
        (PENDING, _("Uploaded")),
        (QUEUED, _("Queued")),
        (RUNNING, _("Running")),
        (DONE, _("Done")),
        (FAILED, _("Failed")),
    ]

    BACKUP = "backup"
    UPLOAD = "upload"

    SOURCE_CHOICES = [
        (BACKUP, _("Backup")),
        (UPLOAD, _("Uploaded file")),
    ]

    database = models.CharField(_("database"), max_length=100, default="default")
    status = models.CharField(
        _("status"), max_length=20, choices=STATUS_CHOICES, default=QUEUED
    )
    source = models.CharField(
        _("source"), max_length=20, choices=SOURCE_CHOICES, default=BACKUP
    )
    backup = models.ForeignKey(
        Backup,
        verbose_name=_("backup"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # The file's name in the backup storage, and the name shown for it.
    file = models.CharField(_("file"), max_length=500, blank=True)
    name = models.CharField(_("name"), max_length=255, blank=True)
    # Bytes, of an upload.
    size = models.BigIntegerField(_("size"), null=True, blank=True)
    # What the file holds, as the restore dialog shows it.
    preview = models.JSONField(_("preview"), default=dict, blank=True)
    make_safety_backup = models.BooleanField(_("back up first"), default=True)
    ignore_migrations = models.BooleanField(_("ignore migrations"), default=False)
    safety_backup = models.ForeignKey(
        Backup,
        verbose_name=_("safety backup"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    rows = models.BigIntegerField(_("rows"), null=True, blank=True)
    error = models.TextField(_("error"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        verbose_name = _("restore")
        verbose_name_plural = _("restores")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["database", "status", "-created_at"])]

    def __str__(self):
        return self.name or self.file or f"{self.database} ({self.status})"

    @property
    def duration(self):
        """Seconds the restore took, once it finished."""
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at).total_seconds())
        return None
