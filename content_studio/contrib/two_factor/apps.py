from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioTwoFactorConfig(AppConfig):
    name = "content_studio.contrib.two_factor"
    label = "content_studio_two_factor"
    # Pinned so the shipped migrations never depend on the project's
    # DEFAULT_AUTO_FIELD.
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = _("Two-factor login")
