from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Version(models.Model):
    """
    An object's values after a change made in the admin, kept with the
    change's activity log entry. data holds every tracked field as the
    edit page has it (see content_studio.snapshots); fields names the
    fields the change touched and previous their values before it.
    """

    log_entry = models.OneToOneField(
        LogEntry, on_delete=models.CASCADE, related_name="content_studio_version"
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name="+"
    )
    object_id = models.CharField(max_length=255)
    fields = models.JSONField(default=list)
    previous = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    data = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("version")
        verbose_name_plural = _("versions")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(
                fields=["content_type", "object_id", "-created_at"],
                name="cs_history_object_idx",
            )
        ]

    def __str__(self):
        return (
            f"{self.content_type} {self.object_id} ({self.created_at:%Y-%m-%d %H:%M})"
        )


class PendingChanges(models.Model):
    """
    Changes saved to a published object that are not live yet, for
    studios whose publishing has pending_changes (see
    content_studio.pending). One row per object: each save updates it,
    Publish changes writes the changes to the object and removes it,
    and Discard removes it.

    data holds each changed field's value as the edit page sent it (a
    new file as {"stored": <name in the field's storage>}), to save it
    the regular way on publish; values holds what the edit page shows
    for those fields.
    """

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name="+"
    )
    object_id = models.CharField(max_length=255)
    fields = models.JSONField(default=list)
    data = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    values = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now)
    edited_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("unpublished changes")
        verbose_name_plural = _("unpublished changes")
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id"],
                name="cs_history_pending_object_unique",
            )
        ]

    def __str__(self):
        return f"{self.content_type} {self.object_id} (unpublished changes)"
