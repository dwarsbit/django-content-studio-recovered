from django.core.management.base import BaseCommand

from content_studio.publishing import run_scheduled


class Command(BaseCommand):
    help = (
        "Record the content that went live or expired on schedule: the "
        "activity log, content_changed (webhooks, notifications), the "
        "status field and the studio's on_publish/on_unpublish hooks. Run "
        "it every minute from cron when Huey is not installed."
    )

    def handle(self, *args, **options):
        result = run_scheduled()

        if options["verbosity"] > 0:
            self.stdout.write(
                f"Published {result['published']}, unpublished "
                f"{result['unpublished']} on schedule."
            )
