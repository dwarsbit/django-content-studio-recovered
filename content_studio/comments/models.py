from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class Comment(models.Model):
    """
    A comment on one object. A comment without a parent starts a
    thread, which can be resolved; replies have the thread's first
    comment as their parent.
    """

    class Meta:
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="cs_comment_target")
        ]

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("Model"),
    )
    object_id = models.CharField(max_length=255)
    tenant = models.CharField(max_length=255, blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Author"),
    )
    body = models.TextField(verbose_name=_("Comment"))
    # What posted the comment besides a person writing it, such as
    # "review.submitted" for the note of a review request.
    kind = models.CharField(max_length=40, blank=True, default="")
    # The ids of the users the comment mentions.
    mentions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    # A deleted comment with replies stays as "Comment deleted", with
    # its body cleared.
    deleted_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    def __str__(self):
        return self.body[:50]
