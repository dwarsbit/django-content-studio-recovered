from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioStatusConfig(AppConfig):
    name = "content_studio.contrib.status"
    label = "content_studio_status"
    verbose_name = _("System status")

    def ready(self):
        from .builtin import register_builtin_services

        register_builtin_services()
