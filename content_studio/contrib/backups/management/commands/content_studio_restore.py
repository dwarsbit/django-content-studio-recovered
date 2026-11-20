from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = (
        "Replace a database's contents with a backup: every table is "
        "emptied and the backup loaded, in one transaction. The backup is "
        "a name in the backup storage (see content_studio_backup --list) "
        "or a file on disk: a Content Studio backup or any JSON file "
        "made with dumpdata (.json, .json.gz, .json.bz2, .json.xz or "
        ".json.lzma). The current data is backed up first."
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
            help="Restore although the backup's migrations differ, or a file "
            "without a manifest (such as a dumpdata file).",
        )
        parser.add_argument(
            "--no-safety-backup",
            action="store_false",
            dest="safety_backup",
            help="Do not back up the current data before the restore.",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Do not ask to confirm.",
        )

    def handle(self, *args, backup=None, latest=False, database="default", **options):
        from ...backup import (
            RestoreError,
            database_name,
            latest_backup,
            make_safety_backup,
            restore,
        )

        if database not in connections.databases:
            raise CommandError(f"There is no database {database!r}.")

        if latest:
            record = latest_backup(database)
            if record is None:
                raise CommandError(f"There is no backup of {database!r}.")
            backup = record.file
        elif not backup:
            raise CommandError("Name a backup, or pass --latest.")

        name = database_name(database)

        if options["interactive"]:
            self.stdout.write(
                f"This replaces everything in the database {name} ({database}) "
                f"with the backup {backup}."
            )
            answer = input(f"Type the database's name ({name}) to continue: ")

            if answer.strip() != name:
                raise CommandError("Restore cancelled.")

        verbose = options["verbosity"] > 0

        def before_load(_preview):
            if not options["safety_backup"]:
                return

            safety = make_safety_backup(database)

            if verbose:
                self.stdout.write(f"Backed up the current data: {safety.file}")

        try:
            preview = restore(
                backup,
                database,
                ignore_migrations=options["ignore_migrations"],
                before_load=before_load,
            )
        except RestoreError as exc:
            raise CommandError(str(exc))

        if verbose:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Restored {backup} into {database} ({preview['rows']} rows)."
                )
            )
