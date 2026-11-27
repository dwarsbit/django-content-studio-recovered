from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def create_tables(sender, using="default", **kwargs):
    """After migrate: the tables of a db:// cache and a db:// task queue."""
    from django.conf import settings
    from django.core.management import call_command

    from .sections import SQL_HUEY

    call_command("createcachetable", database=using, verbosity=0)

    huey = getattr(settings, "HUEY", None)
    sql_queue = isinstance(huey, dict) and huey.get("huey_class") == SQL_HUEY

    if using == "default" and sql_queue:
        from huey.contrib.djhuey import HUEY

        HUEY.storage.create_tables()


class ContentStudioSettingsConfig(AppConfig):
    name = "content_studio.contrib.settings"
    label = "content_studio_settings"
    verbose_name = _("Environment settings")

    def ready(self):
        from . import checks  # noqa: F401 - registers the deploy checks

        post_migrate.connect(
            create_tables,
            sender=self,
            dispatch_uid="content_studio_settings_create_tables",
        )
