from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioPreferencesConfig(AppConfig):
    name = "content_studio.preferences"
    label = "content_studio_preferences"
    verbose_name = _("Preferences")
