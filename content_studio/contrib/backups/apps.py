from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioBackupsConfig(AppConfig):
    name = "content_studio.contrib.backups"
    label = "content_studio_backups"
    verbose_name = _("Backups")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .huey import register_periodic_task
        from .status import register

        register()
        register_periodic_task()
