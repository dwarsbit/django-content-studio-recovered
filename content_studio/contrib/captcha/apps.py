from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioCaptchaConfig(AppConfig):
    name = "content_studio.contrib.captcha"
    label = "content_studio_captcha"
    verbose_name = _("Captcha")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import checks  # noqa: F401 - registers the system checks
