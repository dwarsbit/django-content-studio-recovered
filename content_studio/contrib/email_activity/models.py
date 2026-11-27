from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SentEmail(models.Model):
    """
    One email the site sent, or tried to: its addresses, subject and
    attachments' names, how it went and when. Never its body.
    """

    SENT = "sent"
    FAILED = "failed"

    STATUS_CHOICES = [
        (SENT, _("Sent")),
        (FAILED, _("Failed")),
    ]

    from_email = models.CharField(_("from"), max_length=500, blank=True)
    to = models.JSONField(_("to"), default=list, blank=True)
    cc = models.JSONField(_("cc"), default=list, blank=True)
    bcc = models.JSONField(_("bcc"), default=list, blank=True)
    reply_to = models.JSONField(_("reply to"), default=list, blank=True)
    # Every address it went to, for searching.
    recipients = models.TextField(_("recipients"), blank=True)
    subject = models.TextField(_("subject"), blank=True)
    # What the email is: "invite", "notification_digest" or an app's own.
    kind = models.CharField(_("kind"), max_length=50, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES)
    error = models.TextField(_("error"), blank=True)
    # The backend that delivered it, as the page shows it.
    backend = models.CharField(_("backend"), max_length=200, blank=True)
    message_id = models.CharField(_("message ID"), max_length=255, blank=True)
    # Names, types and sizes; never the contents.
    attachments = models.JSONField(_("attachments"), default=list, blank=True)
    # Bytes of the whole message.
    size = models.PositiveIntegerField(_("size"), null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("sent by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # When it was handed to the backend, and when the backend returned.
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)
    # Milliseconds the backend took.
    duration = models.PositiveIntegerField(_("duration"), null=True, blank=True)

    class Meta:
        verbose_name = _("sent email")
        verbose_name_plural = _("sent emails")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return self.subject or self.recipients or f"#{self.pk}"
