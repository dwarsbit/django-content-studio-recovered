from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SignInEvent(models.Model):
    """
    One sign-in, failed sign-in or sign-out in the admin: who (the user
    when known, and the username as typed), how, from which address and
    browser, and why a failed one failed. Never a password or code.
    """

    SIGNED_IN = "signed_in"
    FAILED = "sign_in_failed"
    SIGNED_OUT = "signed_out"

    KIND_CHOICES = [
        (SIGNED_IN, _("Signed in")),
        (FAILED, _("Failed sign-in")),
        (SIGNED_OUT, _("Signed out")),
    ]

    kind = models.CharField(_("kind"), max_length=20, choices=KIND_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # The username as typed (failed sign-ins), else the user's.
    username = models.CharField(_("username"), max_length=255, blank=True)
    # "password", "two_factor", "recovery_code", "link" or a login
    # backend's name.
    method = models.CharField(_("method"), max_length=100, blank=True)
    # Why a sign-in failed: "wrong_password", "not_allowed", "locked",
    # "wrong_code" or "wrong_recovery_code".
    reason = models.CharField(_("reason"), max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=500, blank=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("sign-in event")
        verbose_name_plural = _("sign-in events")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["-created_at", "-id"], name="cs_audit_signin_time_idx"
            ),
            models.Index(
                fields=["user", "-created_at"], name="cs_audit_signin_user_idx"
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.username} ({self.created_at:%Y-%m-%d %H:%M})"


class EntryAction(models.Model):
    """
    The action an activity log entry recorded, for the actions LogEntry's
    three flags cannot tell apart: restored, reordered, published and
    unpublished are all a change to it. Written by record_change() while
    the app is installed; older entries go by their flag.
    """

    log_entry = models.OneToOneField(
        LogEntry,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="content_studio_action",
    )
    action = models.CharField(_("action"), max_length=20, db_index=True)

    class Meta:
        verbose_name = _("entry action")
        verbose_name_plural = _("entry actions")

    def __str__(self):
        return f"{self.log_entry_id}: {self.action}"
