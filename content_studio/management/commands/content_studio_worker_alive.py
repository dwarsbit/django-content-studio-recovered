from django.core.management.base import BaseCommand, CommandError

from content_studio.health import OFF, OK, check_worker, get_last_beat


class Command(BaseCommand):
    help = (
        "Exit 1 when the worker's heartbeat is missing or older than "
        "HEALTH_WORKER_STALE_AFTER, for the worker container's healthcheck. "
        "Exits 0 when there is no worker to watch (tasks run in the "
        "request, or the cache isn't shared)."
    )

    def handle(self, *args, **options):
        result = check_worker()

        if result.status == OK:
            if options["verbosity"] > 0:
                self.stdout.write(f"Worker alive, last heartbeat {get_last_beat()}.")
            return

        if result.status == OFF:
            if options["verbosity"] > 0:
                self.stdout.write(f"Worker check is off: {result.message}")
            return

        raise CommandError(str(result.message))
