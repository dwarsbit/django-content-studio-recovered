from django.core.management.base import BaseCommand

from ...pruning import prune
from ...tasks import PRUNING_TASK, record_run


class Command(BaseCommand):
    help = (
        "Remove read notifications older than NOTIFICATION_RETENTION days "
        "and unread ones older than NOTIFICATION_UNREAD_RETENTION days, "
        "follows of objects that no longer exist, and subscriptions to "
        "models that no longer exist. Huey's worker runs it daily at "
        "04:30; without Huey, run it daily from cron."
    )

    def handle(self, *args, **options):
        try:
            notifications, follows, subscriptions = prune()
        except Exception as error:
            record_run(PRUNING_TASK, error)
            raise

        record_run(PRUNING_TASK)
        self.stdout.write(
            f"Removed {notifications} notifications, {follows} follows and "
            f"{subscriptions} subscriptions."
        )
