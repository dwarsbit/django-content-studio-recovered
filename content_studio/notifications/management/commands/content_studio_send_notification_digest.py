from django.core.management.base import BaseCommand, CommandError

from ...digest import DEFAULT_DELAY, digest_available, send_digests
from ...tasks import DIGEST_TASK, record_run


class Command(BaseCommand):
    help = (
        "Email every editor the notifications they have not read, once: "
        "unread ones that did not change for --delay minutes and were not "
        "mailed before. Needs NOTIFICATION_EMAIL_DIGEST and ADMIN_URL. "
        "Huey's worker runs it every hour at :10; without Huey, run it "
        "hourly from cron."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay",
            type=int,
            default=DEFAULT_DELAY,
            help=(
                "Minutes a notification stays unread and unchanged before it "
                f"is mailed (default {DEFAULT_DELAY})."
            ),
        )

    def handle(self, *args, delay, **options):
        if not digest_available():
            raise CommandError(
                "The notification digest is off: set NOTIFICATION_EMAIL_DIGEST "
                "to True and ADMIN_URL to the admin's absolute URL."
            )

        if delay < 0:
            raise CommandError("--delay must be 0 or more minutes.")

        try:
            emails, notifications = send_digests(delay=delay)
        except Exception as error:
            record_run(DIGEST_TASK, error)
            raise

        record_run(DIGEST_TASK)
        self.stdout.write(f"Sent {emails} emails with {notifications} notifications.")
