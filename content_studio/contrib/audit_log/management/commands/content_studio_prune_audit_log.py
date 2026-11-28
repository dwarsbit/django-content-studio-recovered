from django.core.management.base import BaseCommand

from .....settings import cs_settings


class Command(BaseCommand):
    help = (
        "Delete the activity log entries and sign-in events older than "
        "AUDIT_LOG_KEEP_DAYS, with the history versions of those entries. "
        "The audit log is also pruned after a sign-in, at most once an hour."
    )

    def handle(self, *args, **options):
        from ...recording import prune

        days = cs_settings.AUDIT_LOG_KEEP_DAYS

        if days is None:
            self.stdout.write("AUDIT_LOG_KEEP_DAYS is None: every entry is kept.")
            return

        entries, events = prune()
        self.stdout.write(
            f"Deleted {entries} activity log entries and {events} sign-in events "
            f"older than {days} days."
        )
