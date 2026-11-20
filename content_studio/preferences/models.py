from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserPreferences(models.Model):
    """
    An editor's own settings for the admin, chosen on their profile page.
    A user without a row has the defaults.
    """

    class SaveAction(models.TextChoices):
        SAVE = "save", _("Save")
        ADD_ANOTHER = "add_another", _("Save and add another")
        CLOSE = "close", _("Save and close")

    # The user is the primary key: one row per user, and no id field
    # that would depend on the project's DEFAULT_AUTO_FIELD.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="content_studio_preferences",
        verbose_name=_("User"),
    )
    # What the edit page's Save button does; the menu next to it offers
    # the others.
    save_action = models.CharField(
        max_length=20,
        choices=SaveAction.choices,
        default=SaveAction.SAVE,
        verbose_name=_("Default save action"),
    )

    class Meta:
        verbose_name = _("user preferences")
        verbose_name_plural = _("user preferences")

    def __str__(self):
        return str(self.user)
