from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentStudioPreviewsConfig(AppConfig):
    """
    Shared draft links: the optional app that stores them. Staff
    previews work without it.
    """

    name = "content_studio.previews"
    label = "content_studio_previews"
    # Pinned so the shipped migrations never depend on the project's
    # DEFAULT_AUTO_FIELD.
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = _("Previews")

    def ready(self):
        from django.db.models.signals import post_migrate

        from .permissions import create_permissions

        post_migrate.connect(
            create_permissions, dispatch_uid="content_studio_share_permissions"
        )
