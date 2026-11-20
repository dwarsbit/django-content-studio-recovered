from django.apps import AppConfig


class BlogConfig(AppConfig):
    name = "demo.blog"
    label = "demo_blog"
    verbose_name = "Blog"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from content_studio.contrib import status

        from .task_queue import demo_task_adapter

        # The status page (user menu, System status) shows the demo's
        # made-up task queue and two made-up services; the backups app
        # adds the real nightly backup.
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
