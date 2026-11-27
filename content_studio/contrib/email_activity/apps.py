from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioEmailActivityConfig(AppConfig):
    name = "content_studio.contrib.email_activity"
    label = "content_studio_email_activity"
    verbose_name = _("Email activity")
    default_auto_field = "django.db.models.BigAutoField"
