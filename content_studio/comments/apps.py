from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioCommentsConfig(AppConfig):
    name = "content_studio.comments"
    label = "content_studio_comments"
    # Pinned so the shipped migrations never depend on the project's
    # DEFAULT_AUTO_FIELD.
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = _("Comments")

    def ready(self):
        from django.db.models.signals import post_delete

        from .notifying import register_events
        from .signals import delete_comments

        register_events()
        post_delete.connect(delete_comments, dispatch_uid="content_studio_comments")
