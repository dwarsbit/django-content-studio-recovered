from django.apps import AppConfig


class BlogConfig(AppConfig):
    name = "demo.blog"
    label = "demo_blog"
    verbose_name = "Blog"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.utils import timezone

        from content_studio.contrib import status

        from .task_queue import demo_task_adapter

        # The status page (user menu, System status) shows the demo's
        # made-up task queue, two made-up services and a nightly job.
        status.register_task_adapter(demo_task_adapter)
        status.register_service(
            "blog.search",
            "Search index",
            lambda: status.ok("Meilisearch · 12,480 documents"),
            icon="ph-bold ph-magnifying-glass",
        )
        status.register_service(
            "blog.cdn",
            "CDN",
            lambda: status.degraded(
                "Fastly", message="Purges take longer than usual: 45 s."
            ),
            icon="ph-bold ph-globe-hemisphere-west",
        )
        status.register_recurring_task(
            "blog.backup",
            "Back up the database",
            "Daily at 02:00",
            get_last_run=lambda: timezone.now() - timezone.timedelta(hours=6),
            get_next_run=lambda: timezone.now() + timezone.timedelta(hours=18),
            group="Blog",
        )
