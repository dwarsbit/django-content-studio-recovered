from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = (
        "Replace a database's contents with a backup: every table is "
        "emptied and the backup loaded, in one transaction. The backup is "
        "a name in the backup storage (see content_studio_backup --list) "
        "or a file on disk."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "backup",
            nargs="?",
            help="The backup's name in the backup storage, or a file path.",
        )
        parser.add_argument(
            "--latest",
            action="store_true",
            help="Restore the newest backup of the database.",
        )
        parser.add_argument(
            "--database",
            default="default",
            help='The database alias to restore into ("default").',
        )
        parser.add_argument(
            "--ignore-migrations",
            action="store_true",
            help="Restore although the backup's migrations differ.",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Do not ask to confirm.",
        )

    def handle(self, *args, backup=None, latest=False, database="default", **options):
        from ...backup import RestoreError, latest_backup, restore

        if database not in connections.databases:
            raise CommandError(f"There is no database {database!r}.")

        if latest:
            record = latest_backup(database)
            if record is None:
                raise CommandError(f"There is no backup of {database!r}.")
            backup = record.file
        elif not backup:
            raise CommandError("Name a backup, or pass --latest.")

        name = connections[database].settings_dict.get("NAME") or database

        if options["interactive"]:
            self.stdout.write(
                f"This replaces everything in the database {name} ({database}) "
                f"with the backup {backup}."
            )
            answer = input(f"Type the database's name ({name}) to continue: ")

            if answer.strip() != str(name):
                raise CommandError("Restore cancelled.")

        try:
            manifest = restore(
                backup,
                database,
                ignore_migrations=options["ignore_migrations"],
            )
        except RestoreError as exc:
            raise CommandError(str(exc))

        if options["verbosity"] > 0:
            rows = sum(
                count
                for count in ((manifest or {}).get("counts") or {}).values()
                if count
            )
            self.stdout.write(
                self.style.SUCCESS(f"Restored {backup} into {database} ({rows} rows).")
            )
