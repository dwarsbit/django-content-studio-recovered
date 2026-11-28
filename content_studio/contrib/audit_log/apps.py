from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioAuditLogConfig(AppConfig):
    name = "content_studio.contrib.audit_log"
    label = "content_studio_audit_log"
    verbose_name = _("Audit log")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import recording

        recording.connect()
