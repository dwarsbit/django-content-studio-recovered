from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import filesizeformat


class Command(BaseCommand):
    help = (
        "Back up the databases in BACKUP_DATABASES to the backup storage, "
        "keeping the newest BACKUP_KEEP. Run it from cron when Huey does "
        "not run the backups."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            action="append",
            dest="databases",
            help="A database alias to back up (repeat for more); "
            "BACKUP_DATABASES by default.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_backups",
            help="List the backups instead of making one.",
        )

    def handle(self, *args, databases=None, list_backups=False, **options):
        from ...backup import BackupError, clean_uploads, get_databases, make_backup
        from ...models import Backup

        if list_backups:
            for backup in Backup.objects.all():
                self.stdout.write(
                    "\t".join(
                        [
                            backup.created_at.isoformat(timespec="seconds"),
                            backup.database,
                            backup.status,
                            filesizeformat(backup.size) if backup.size else "",
                            backup.file or backup.error,
                        ]
                    )
                )
            return

        failed = []

        for alias in databases or get_databases():
            try:
                backup = make_backup(alias, Backup.COMMAND)
            except BackupError as exc:
                failed.append(alias)
                self.stderr.write(f"{alias}: {exc}")
                continue

            if options["verbosity"] > 0:
                self.stdout.write(
                    f"{alias}: {backup.file} ({filesizeformat(backup.size)})"
                )

        clean_uploads()

        if failed:
            raise CommandError(f"The backup of {', '.join(failed)} failed.")
