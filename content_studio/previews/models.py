from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class PreviewLink(models.Model):
    """
    A shared draft link: anyone with its key may see one object on the
    site while it is not live, until expires_at (None: until revoked).
    Revoking deletes the row. Only a hash of the key is kept; the key
    itself is shown once, when the link is made.
    """

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, verbose_name=_("content type")
    )
    object_id = models.CharField(_("object id"), max_length=255)
    # The content language the link opens in; empty for the site's own.
    language = models.CharField(_("language"), max_length=15, blank=True)
    key_hash = models.CharField(_("key hash"), max_length=64, unique=True)
    note = models.CharField(_("note"), max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    opens = models.PositiveIntegerField(_("opens"), default=0)
    last_opened_at = models.DateTimeField(_("last opened at"), null=True, blank=True)

    class Meta:
        verbose_name = _("shared draft link")
        verbose_name_plural = _("shared draft links")
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return self.note or f"{self.content_type_id}:{self.object_id}"
