from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioReviewConfig(AppConfig):
    name = "content_studio.review"
    label = "content_studio_review"
    # Pinned so the shipped migrations never depend on the project's
    # DEFAULT_AUTO_FIELD.
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = _("Review")

    def ready(self):
        from django.db.models.signals import post_delete

        from .notifying import register_events
        from .signals import delete_requests

        register_events()
        post_delete.connect(delete_requests, dispatch_uid="content_studio_review")
