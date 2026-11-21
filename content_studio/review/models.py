from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

OPEN = "open"
APPROVED = "approved"
CHANGES_REQUESTED = "changes_requested"
WITHDRAWN = "withdrawn"


class ReviewRequest(models.Model):
    """
    One request to review an object. An object has at most one current
    request (closed_at is None): open (in review) or with changes
    requested. Closed requests stay as the record of who submitted, who
    decided and what was approved.
    """

    class Status(models.TextChoices):
        OPEN = OPEN, _("In review")
        APPROVED = APPROVED, _("Approved")
        CHANGES_REQUESTED = CHANGES_REQUESTED, _("Changes requested")
        WITHDRAWN = WITHDRAWN, _("Withdrawn")

    class Meta:
        verbose_name = _("review request")
        verbose_name_plural = _("review requests")
        ordering = ["-submitted_at", "-pk"]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="cs_review_target"),
            models.Index(fields=["status"], name="cs_review_status"),
        ]

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("Model"),
    )
    object_id = models.CharField(max_length=255)
    object_repr = models.CharField(max_length=200, blank=True, default="")
    tenant = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=OPEN, verbose_name=_("Status")
    )
    # Whether the object was live: the review is of its unpublished
    # changes.
    live = models.BooleanField(default=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Submitted by"),
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    # The person the submitter asked; anyone who may publish may review.
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Reviewer"),
    )
    note = models.TextField(blank=True, default="")
    # The object's values when it was submitted, and their fingerprint:
    # an approval names the fingerprint the reviewer saw.
    snapshot = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=64, blank=True, default="")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")
    # The values that were approved.
    approved_snapshot = models.JSONField(null=True, blank=True)
    # When the request stopped being the object's current one: approved,
    # withdrawn, or followed by a new request. None while it is open or
    # has changes requested.
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.object_repr} ({self.status})"

    @property
    def is_current(self) -> bool:
        return self.closed_at is None
