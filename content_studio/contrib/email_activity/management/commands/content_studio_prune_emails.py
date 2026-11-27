from django.core.management.base import BaseCommand

from .....settings import cs_settings


class Command(BaseCommand):
    help = (
        "Delete the logged emails older than EMAIL_ACTIVITY_KEEP_DAYS. The log "
        "is also pruned after sending, at most once an hour."
    )

    def handle(self, *args, **options):
        from ...log import prune

        days = cs_settings.EMAIL_ACTIVITY_KEEP_DAYS

        if days is None:
            self.stdout.write("EMAIL_ACTIVITY_KEEP_DAYS is None: every email is kept.")
            return

        deleted = prune()
        self.stdout.write(f"Deleted {deleted} emails older than {days} days.")
