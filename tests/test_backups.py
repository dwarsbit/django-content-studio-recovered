"""
Tests for automatic backups: the schedule, making, keeping and restoring
backups, the status page's rows, the Backups page's endpoints, the
commands, Huey's periodic task and the checks.
"""

import datetime
import gzip
import io
import json
import uuid
from unittest import mock

import pytest
from django.contrib.auth import models as auth_models
from django.core.files.storage import storages
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.checks import (
    backup_errors,
    backup_storage_errors,
    backup_warnings,
)
from content_studio.contrib.backups import backup as backups
from content_studio.contrib.backups import huey as backup_huey
from content_studio.contrib.backups import schedule, status
from content_studio.contrib.backups.models import Backup, Restore
from content_studio.contrib.status import ServiceStatus
from content_studio.contrib.status import registry as status_registry
from content_studio.settings import cs_settings
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Article

UTC = datetime.timezone.utc


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.fixture(autouse=True)
def fresh_storage():
    """An empty backup storage per test."""
    storage = storages["backups"]
    storage._root._children.clear()
    yield storage


@pytest.fixture
def superuser(db):
    return auth_models.User.objects.create_user(
        username="root", password="x", is_staff=True, is_superuser=True
    )


@pytest.fixture
def staff(db):
    return auth_models.User.objects.create_user(
        username="editor", password="x", is_staff=True
    )


def daily():
    return mock.patch.object(cs_settings, "BACKUP_SCHEDULE", "0 3 * * *")


# The schedule


def test_schedule_parses_cron_fields():
    parsed = schedule.parse("*/15 1-3 1,15 * 7")

    assert parsed.minute == frozenset({0, 15, 30, 45})
    assert parsed.hour == frozenset({1, 2, 3})
    assert parsed.day == frozenset({1, 15})
    assert parsed.day_of_week == frozenset({0})
    assert parsed.either_day


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "0 3 * *",
        "60 * * * *",
        "0 3 * * 8",
        "a * * * *",
        "*/0 * * * *",
        "5-1 * * * *",
    ],
)
def test_schedule_refuses_what_is_not_cron(expression):
    with pytest.raises(schedule.ScheduleError):
        schedule.parse(expression)


def test_schedule_finds_the_next_run():
    parsed = schedule.parse("0 3 * * *")
    moment = datetime.datetime(2026, 11, 20, 10, 30, tzinfo=UTC)

    assert parsed.next_after(moment) == datetime.datetime(
        2026, 11, 21, 3, 0, tzinfo=UTC
    )
    # Exactly on time: the run after.
    assert parsed.next_after(
        datetime.datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
    ) == datetime.datetime(2026, 11, 22, 3, 0, tzinfo=UTC)


def test_schedule_on_a_weekday_or_a_day_of_the_month():
    # Mondays, and the 1st: either one, as in cron.
    parsed = schedule.parse("0 0 1 * 1")
    moment = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=UTC)  # a Tuesday

    assert parsed.next_after(moment) == datetime.datetime(
        2026, 11, 30, 0, 0, tzinfo=UTC
    )
    assert parsed.next_after(
        datetime.datetime(2026, 11, 30, 1, 0, tzinfo=UTC)
    ) == datetime.datetime(2026, 12, 1, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "expression, words",
    [
        ("0 3 * * *", "Daily at 03:00"),
        ("30 22 * * 0", "Weekly on Sunday at 22:30"),
        ("15 * * * *", "Hourly at :15 past"),
        ("0 */6 * * *", "Every 6 hours"),
        ("0 3 1 * *", "Cron: 0 3 1 * *"),
    ],
)
def test_schedule_in_words(expression, words):
    assert schedule.parse(expression).describe() == words


def test_schedule_gives_huey_its_crontab():
    assert schedule.parse("0 3 * * 7").huey_crontab_kwargs() == {
        "minute": "0",
        "hour": "3",
        "day": "*",
        "month": "*",
        "day_of_week": "0",
    }


# Making a backup


def read_fixture(storage, name):
    with storage.open(name, "rb") as file:
        return json.loads(gzip.decompress(file.read()))


@pytest.mark.django_db
def test_backup_saves_a_fixture_and_its_manifest(fresh_storage):
    Article.objects.create(title="Kept")

    backup = backups.make_backup("default", Backup.COMMAND)

    assert backup.status == Backup.DONE
    assert backup.file.startswith("content_studio/backups/default/")
    assert backup.file.endswith(".json.gz")
    assert backup.size > 0
    assert backup.started_at and backup.finished_at

    objects = read_fixture(fresh_storage, backup.file)
    models = {item["model"] for item in objects}

    assert {"model": "testapp.article"}.items() <= next(
        item for item in objects if item["model"] == "testapp.article"
    ).items()
    assert "contenttypes.contenttype" not in models
    assert "auth.permission" not in models
    assert "sessions.session" not in models
    assert "content_studio_backups.backup" not in models
    assert "password_reset.passwordresetcode" not in models

    with fresh_storage.open(backups.manifest_name(backup.file), "rb") as file:
        manifest = json.loads(file.read())

    assert manifest == backup.manifest
    assert manifest["database"] == "default"
    assert manifest["engine"] == "sqlite"
    assert manifest["counts"]["testapp.Article"] == 1
    assert "0001_initial" in manifest["migrations"]["auth"]


def test_backup_names_cannot_be_guessed_from_the_time():
    moment = datetime.datetime(2026, 11, 21, 3, 0, 0, tzinfo=UTC)

    first = backups.backup_name("default", moment)
    second = backups.backup_name("default", moment)

    assert first != second
    assert first.startswith("content_studio/backups/default/2026-11-21T030000Z-")
    assert first.endswith(".json.gz")
    # 128 random bits between the time and the extension.
    token = first.removeprefix(
        "content_studio/backups/default/2026-11-21T030000Z-"
    ).removesuffix(".json.gz")
    assert len(token) == 32
    assert backups.manifest_name(first) == first.removesuffix(".json.gz") + (
        ".manifest.json"
    )


@pytest.mark.django_db
def test_backup_leaves_out_password_reset_codes():
    from content_studio.contrib.password_reset.models import PasswordResetCode

    assert "password_reset.PasswordResetCode" in backups.get_excludes()
    assert not any(
        model is PasswordResetCode
        for model in backups.get_models("default", backups.get_excludes())
    )


@pytest.mark.django_db
def test_backup_leaves_out_captcha_tokens():
    from content_studio.contrib.captcha.models import Challenge, Token

    assert "content_studio_captcha" in backups.get_excludes()
    models = backups.get_models("default", backups.get_excludes())
    assert Challenge not in models
    assert Token not in models


@pytest.mark.django_db
def test_backup_leaves_out_backup_exclude():
    Article.objects.create(title="Left out")

    with mock.patch.object(cs_settings, "BACKUP_EXCLUDE", ["testapp.Article"]):
        backup = backups.make_backup()

    objects = read_fixture(storages["backups"], backup.file)

    assert "testapp.article" not in {item["model"] for item in objects}
    assert "testapp.Article" not in backup.manifest["counts"]


@pytest.fixture
def placeholder_model():
    """
    A model with managed = False and no table, like a third-party app's
    stand-in for an admin page: dumpdata alone fails on it.
    """
    from django.apps import apps
    from django.db import models

    class Placeholder(models.Model):
        class Meta:
            app_label = "testapp"
            managed = False
            db_table = "testapp_placeholder_without_table"

    yield Placeholder

    del apps.all_models["testapp"]["placeholder"]
    apps.clear_cache()


@pytest.mark.django_db
def test_backup_leaves_out_models_without_a_table(placeholder_model):
    Article.objects.create(title="Kept")

    from django.db import transaction

    # dumpdata on its own stops at the missing table.
    with pytest.raises(CommandError, match="testapp_placeholder_without_table"):
        with transaction.atomic():
            call_command("dumpdata", stdout=io.StringIO(), verbosity=0)

    backup = backups.make_backup()

    assert backup.status == Backup.DONE
    assert backup.manifest["skipped"] == [
        {
            "model": "testapp.Placeholder",
            "tables": ["testapp_placeholder_without_table"],
        }
    ]
    assert "testapp.Placeholder" not in backup.manifest["counts"]

    objects = read_fixture(storages["backups"], backup.file)

    assert "testapp.article" in {item["model"] for item in objects}
    assert "testapp.placeholder" not in {item["model"] for item in objects}


@pytest.mark.django_db
def test_backup_leaves_out_models_whose_many_to_many_table_is_missing():
    from django.db import connection

    through = Article.categories.through._meta.db_table
    table_names = connection.introspection.table_names

    def without_through(*args, **kwargs):
        return [name for name in table_names(*args, **kwargs) if name != through]

    with mock.patch.object(
        connection.introspection, "table_names", side_effect=without_through
    ):
        missing = backups.get_missing_tables("default", backups.get_excludes())

    assert missing == [{"model": "testapp.Article", "tables": [through]}]


@pytest.mark.django_db
def test_backup_has_nothing_to_skip_when_every_table_exists():
    assert backups.get_missing_tables("default", backups.get_excludes()) == []


@pytest.mark.django_db
def test_backups_endpoint_lists_skipped_models(superuser, placeholder_model):
    backups.make_backup()

    response = client_for(superuser).get("/api/backups")

    assert response.status_code == 200
    assert response.json()["backups"][0]["skipped"] == ["testapp.Placeholder"]


@pytest.mark.django_db
def test_a_failed_backup_is_recorded_and_leaves_no_file(fresh_storage):
    with mock.patch.object(backups, "dump", side_effect=RuntimeError("disk full")):
        with pytest.raises(backups.BackupError, match="disk full"):
            backups.make_backup()

    backup = Backup.objects.get()

    assert backup.status == Backup.FAILED
    assert backup.error == "RuntimeError: disk full"
    assert backup.file == ""
    assert backup.finished_at is not None
    assert fresh_storage.listdir("")[0] == []


@pytest.mark.django_db
def test_a_failed_upload_removes_what_was_saved(fresh_storage):
    real_save = fresh_storage.save
    calls = []

    def save(name, content):
        calls.append(name)
        if name.endswith(backups.MANIFEST_EXTENSION):
            raise OSError("bucket gone")
        return real_save(name, content)

    with mock.patch.object(fresh_storage, "save", side_effect=save):
        with pytest.raises(backups.BackupError):
            backups.make_backup()

    assert not fresh_storage.exists(calls[0])
    assert Backup.objects.get().status == Backup.FAILED


@pytest.mark.django_db
def test_one_backup_per_database_at_a_time():
    backups.queue_backup("default", Backup.MANUAL)

    with pytest.raises(backups.BackupRunning):
        backups.queue_backup("default", Backup.MANUAL)


@pytest.mark.django_db
def test_a_backup_that_never_finished_turns_failed():
    stuck = Backup.objects.create(status=Backup.RUNNING)
    Backup.objects.filter(pk=stuck.pk).update(
        created_at=timezone.now() - datetime.timedelta(hours=7)
    )

    assert not backups.is_running("default")

    stuck.refresh_from_db()
    assert stuck.status == Backup.FAILED
    assert stuck.error == "The backup did not finish."


@pytest.mark.django_db
def test_an_unknown_database_is_refused():
    with pytest.raises(backups.BackupError, match="no database"):
        backups.make_backup("elsewhere")


# Keeping backups


@pytest.mark.django_db
def test_only_the_newest_backups_are_kept(fresh_storage):
    with mock.patch.object(cs_settings, "BACKUP_KEEP", 2):
        made = []
        for minutes in (30, 20, 10, 0):
            with mock.patch.object(
                timezone,
                "now",
                return_value=timezone.now() - datetime.timedelta(minutes=minutes),
            ):
                made.append(backups.make_backup())

    kept = list(Backup.objects.order_by("created_at"))

    assert [backup.pk for backup in kept] == [made[2].pk, made[3].pk]
    assert not fresh_storage.exists(made[0].file)
    assert not fresh_storage.exists(backups.manifest_name(made[0].file))
    assert fresh_storage.exists(made[3].file)


@pytest.mark.django_db
def test_failed_runs_older_than_the_kept_backups_go_too():
    with mock.patch.object(cs_settings, "BACKUP_KEEP", 1):
        old_failure = Backup.objects.create(status=Backup.FAILED, error="x")
        Backup.objects.filter(pk=old_failure.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=1)
        )
        backups.make_backup()

    assert not Backup.objects.filter(pk=old_failure.pk).exists()


@pytest.mark.django_db
def test_keep_none_keeps_everything():
    with mock.patch.object(cs_settings, "BACKUP_KEEP", None):
        for _i in range(3):
            backups.make_backup()

    assert Backup.objects.count() == 3


# Restoring a backup


@pytest.mark.django_db
def test_restore_brings_the_database_back(superuser):
    article = Article.objects.create(title="Before", author=superuser)
    group = auth_models.Group.objects.create(name="Editors")
    group.permissions.add(auth_models.Permission.objects.get(codename="add_article"))
    backup = backups.make_backup()

    Article.objects.all().delete()
    Article.objects.create(title="After")
    group.delete()

    backups.restore(backup.file)

    assert list(Article.objects.values_list("pk", "title", "author_id")) == [
        (article.pk, "Before", superuser.pk)
    ]
    restored = auth_models.Group.objects.get(name="Editors")
    assert list(restored.permissions.values_list("codename", flat=True)) == [
        "add_article"
    ]
    # The backup records survive the restore.
    assert Backup.objects.filter(pk=backup.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_backups_and_restores_after_a_restore_get_new_ids(superuser):
    # Emptying the database resets its sequences; the records put back
    # keep their ids, so the sequences must move past them again.
    first = backups.make_backup()
    second = backups.make_backup()
    earlier = Restore.objects.create(
        database="default",
        source=Restore.UPLOAD,
        name="old.json.gz",
        status=Restore.DONE,
    )

    backups.restore(first.file)

    after = backups.make_backup()
    restore = Restore.objects.create(
        database="default",
        source=Restore.UPLOAD,
        name="new.json.gz",
        status=Restore.DONE,
    )

    assert after.status == Backup.DONE
    assert after.pk > second.pk
    assert restore.pk > earlier.pk


@pytest.mark.django_db
def test_restore_from_a_file_on_disk(tmp_path):
    Article.objects.create(title="On disk")
    backup = backups.make_backup()
    path = tmp_path / "copy.json.gz"
    path.write_bytes(storages["backups"].open(backup.file, "rb").read())
    (tmp_path / "copy.manifest.json").write_text(json.dumps(backup.manifest))

    Article.objects.all().delete()
    backups.restore(str(path))

    assert Article.objects.filter(title="On disk").exists()


@pytest.mark.django_db
def test_restore_refuses_other_migrations(fresh_storage):
    backup = backups.make_backup()
    manifest = dict(backup.manifest)
    manifest["migrations"] = {
        **manifest["migrations"],
        "auth": [*manifest["migrations"]["auth"], "9999_future"],
    }
    fresh_storage.delete(backups.manifest_name(backup.file))
    fresh_storage.save(
        backups.manifest_name(backup.file),
        io.BytesIO(json.dumps(manifest).encode()),
    )
    Article.objects.create(title="Stays")

    with pytest.raises(
        backups.RestoreError, match="Only in the backup: auth.9999_future"
    ):
        backups.restore(backup.file)

    assert Article.objects.filter(title="Stays").exists()

    backups.restore(backup.file, ignore_migrations=True)
    assert not Article.objects.filter(title="Stays").exists()


@pytest.mark.django_db
def test_restore_of_a_missing_backup():
    with pytest.raises(backups.RestoreError, match="no backup"):
        backups.restore("content_studio/backups/default/nope.json.gz")


# On the status page


def check():
    return status.check_backups()


@pytest.mark.django_db
def test_status_without_backups_is_degraded():
    with daily():
        result = check()

    assert result.status == ServiceStatus.DEGRADED
    assert result.message == "No backup has been made yet."


@pytest.mark.django_db
def test_status_after_a_backup_is_ok():
    with daily():
        backups.make_backup()
        result = check()

    assert result.status == ServiceStatus.OK
    assert result.detail.startswith("Last backup just now · ")


@pytest.mark.django_db
def test_status_after_a_failed_backup_is_down():
    with daily():
        backups.make_backup()
        Backup.objects.create(status=Backup.FAILED, error="RuntimeError: boom")
        result = check()

    assert result.status == ServiceStatus.DOWN
    assert "boom" in result.message


@pytest.mark.django_db
def test_status_of_an_overdue_backup_is_degraded():
    with daily():
        backup = backups.make_backup()
        Backup.objects.filter(pk=backup.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=3),
            started_at=timezone.now() - datetime.timedelta(days=3),
        )
        result = check()

    assert result.status == ServiceStatus.DEGRADED
    assert "overdue" in result.message


@pytest.mark.django_db
def test_status_without_a_schedule_is_unknown():
    backups.make_backup()

    assert check().status == ServiceStatus.UNKNOWN


@pytest.mark.django_db
def test_status_of_a_missing_storage_is_down():
    with mock.patch.object(cs_settings, "BACKUP_STORAGE", "nowhere"):
        result = check()

    assert result.status == ServiceStatus.DOWN


def test_the_service_links_to_the_backups_page():
    service = next(
        s for s in status_registry.get_services() if s.key == status.SERVICE_KEY
    )

    assert service.url == "backups"


@pytest.fixture
def clean_registry():
    names = ("_services", "_recurring", "_task_labels", "_errors")
    saved = {name: getattr(status_registry, name).copy() for name in names}
    yield
    for name in names:
        value = getattr(status_registry, name)
        value.clear()
        if isinstance(value, dict):
            value.update(saved[name])
        else:
            value.extend(saved[name])


@pytest.mark.django_db
def test_the_recurring_backup_is_registered_with_a_schedule(clean_registry):
    status_registry._recurring.pop(status.RECURRING_KEY, None)

    with daily():
        status.register()
        task = status_registry._recurring[status.RECURRING_KEY]

        assert str(task.schedule) == "Daily at 03:00"
        assert task.get_next_run() > timezone.now()
        assert task.get_last_run() is None

        backups.make_backup()
        run = task.get_last_run()

    assert run.ok and run.at is not None


# The Backups page


@pytest.mark.django_db
def test_the_page_is_for_superusers(staff):
    assert client_for(staff).get("/api/backups").status_code == 403


@pytest.mark.django_db
def test_the_page_lists_the_backups(superuser):
    backups.make_backup()

    with daily():
        response = client_for(superuser).get("/api/backups")

    assert response.status_code == 200
    data = response.json()
    assert data["schedule"] == "Daily at 03:00"
    assert data["keep"] == 14
    assert data["databases"] == ["default"]
    assert data["storage"] == "InMemoryStorage"
    [row] = data["backups"]
    assert row["status"] == "done"
    assert row["name"].endswith(".json.gz")


@pytest.mark.django_db(transaction=True)
@override_settings(
    TASKS={"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
)
def test_back_up_now(superuser):
    client = client_for(superuser)
    response = client.post("/api/backups")

    assert response.status_code == 202
    backup = Backup.objects.get()
    assert backup.trigger == Backup.MANUAL
    assert backup.created_by == superuser
    assert backup.status == Backup.DONE


@pytest.mark.django_db
@override_settings(
    TASKS={"default": {"BACKEND": "django.tasks.backends.dummy.DummyBackend"}}
)
def test_back_up_now_twice_is_refused(superuser):
    client = client_for(superuser)

    assert client.post("/api/backups").status_code == 202
    assert client.post("/api/backups").status_code == 409


@pytest.mark.django_db
def test_download(superuser, staff):
    backup = backups.make_backup()
    response = client_for(superuser).get(f"/api/backups/{backup.pk}/download")

    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert gzip.decompress(b"".join(response.streaming_content))
    assert (
        client_for(staff).get(f"/api/backups/{backup.pk}/download").status_code == 403
    )


@pytest.mark.django_db
def test_download_of_a_failed_backup_is_not_found(superuser):
    backup = Backup.objects.create(status=Backup.FAILED)

    response = client_for(superuser).get(f"/api/backups/{backup.pk}/download")

    assert response.status_code == 404


@pytest.mark.django_db
def test_discover_tells_who_has_the_page(superuser, staff):
    assert client_for(superuser).get("/api/discover").json()["backups"] == {
        "enabled": True
    }
    assert client_for(staff).get("/api/discover").json()["backups"] == {
        "enabled": False
    }


# The commands


@pytest.mark.django_db
def test_backup_command(capsys):
    call_command("content_studio_backup")

    backup = Backup.objects.get()
    assert backup.trigger == Backup.COMMAND
    assert backup.file in capsys.readouterr().out

    call_command("content_studio_backup", "--list")
    assert backup.file in capsys.readouterr().out


@pytest.mark.django_db
def test_backup_command_fails_loudly():
    with mock.patch.object(backups, "dump", side_effect=RuntimeError("boom")):
        with pytest.raises(CommandError, match="default failed"):
            call_command("content_studio_backup", stderr=io.StringIO())


@pytest.mark.django_db
def test_restore_command_latest():
    Article.objects.create(title="Back")
    backups.make_backup()
    Article.objects.all().delete()

    call_command("content_studio_restore", "--latest", "--noinput", verbosity=0)

    assert Article.objects.filter(title="Back").exists()


@pytest.mark.django_db
def test_restore_command_asks_for_the_database_name():
    backup = backups.make_backup()
    Article.objects.create(title="Stays")

    with mock.patch("builtins.input", return_value="wrong"):
        with pytest.raises(CommandError, match="cancelled"):
            call_command("content_studio_restore", backup.file, stdout=io.StringIO())

    assert Article.objects.filter(title="Stays").exists()


def test_restore_command_needs_a_backup():
    with pytest.raises(CommandError, match="--latest"):
        call_command("content_studio_restore", "--noinput")


# Restoring dumpdata files


def test_prepare_matches_content_types_and_permissions_by_name():
    from content_studio.contrib.backups import fixtures

    rows = [
        {
            "model": "contenttypes.contenttype",
            "pk": 900,
            "fields": {"app_label": "testapp", "model": "article"},
        },
        {
            "model": "auth.permission",
            "pk": 9001,
            "fields": {
                "name": "Can add article",
                "content_type": 900,
                "codename": "add_article",
            },
        },
        {
            "model": "auth.group",
            "pk": 3,
            "fields": {"name": "Editors", "permissions": [9001]},
        },
        {"model": "sessions.session", "pk": "abc", "fields": {}},
        {"model": "content_studio_backups.backup", "pk": 1, "fields": {}},
        {"model": "shop.order", "pk": 1, "fields": {}},
    ]

    fixture = fixtures.prepare(rows)

    [group] = fixture.rows
    assert group["fields"]["permissions"] == [["add_article", "testapp", "article"]]
    assert fixture.counts == {"auth.Group": 1}
    assert fixture.skipped == 4
    assert fixture.remapped == 1
    assert fixture.unknown_models == ["shop.order"]


def test_prepare_refuses_an_id_the_file_does_not_hold():
    from content_studio.contrib.backups import fixtures

    rows = [
        {"model": "auth.group", "pk": 3, "fields": {"name": "E", "permissions": [7]}}
    ]

    with pytest.raises(fixtures.FixtureError, match="permission 7"):
        fixtures.prepare(rows)


@pytest.mark.django_db
@pytest.mark.parametrize("suffix", [".json", ".json.gz", ".json.bz2", ".json.xz"])
def test_restore_a_plain_dumpdata_file(tmp_path, suffix, superuser):
    group = auth_models.Group.objects.create(name="Editors")
    group.permissions.add(auth_models.Permission.objects.get(codename="add_article"))
    Article.objects.create(title="Dumped", author=superuser)
    # A backup record in the file: the restore keeps its own records.
    Backup.objects.create(status=Backup.DONE, file="old.json.gz")
    path = str(tmp_path / f"site{suffix}")
    call_command("dumpdata", output=path, verbosity=0)

    Article.objects.all().delete()
    group.delete()

    with pytest.raises(backups.RestoreError, match="no manifest"):
        backups.restore(path)

    preview = backups.restore(path, ignore_migrations=True)

    assert Article.objects.filter(title="Dumped").exists()
    restored = auth_models.Group.objects.get(name="Editors")
    assert list(restored.permissions.values_list("codename", flat=True)) == [
        "add_article"
    ]
    assert preview["manifest"] is False
    assert preview["rows"] >= 3
    assert Backup.objects.count() == 1


@pytest.mark.django_db
def test_restore_refuses_other_files(tmp_path):
    path = tmp_path / "site.xml"
    path.write_text("<django-objects/>")

    with pytest.raises(backups.RestoreError, match="not a JSON fixture"):
        backups.restore(str(path), ignore_migrations=True)

    path = tmp_path / "site.json"
    path.write_text('{"not": "a list"}')

    with pytest.raises(backups.RestoreError, match="not a Django fixture"):
        backups.restore(str(path), ignore_migrations=True)


@pytest.mark.django_db
def test_restore_refuses_models_that_are_not_installed(tmp_path):
    path = tmp_path / "site.json"
    path.write_text(json.dumps([{"model": "shop.order", "pk": 1, "fields": {}}]))
    Article.objects.create(title="Stays")

    with pytest.raises(backups.RestoreError, match="not installed: shop.order"):
        backups.restore(str(path), ignore_migrations=True)

    assert Article.objects.filter(title="Stays").exists()


@pytest.mark.django_db
def test_before_load_runs_after_the_checks(tmp_path):
    path = tmp_path / "site.json"
    path.write_text(json.dumps([{"model": "shop.order", "pk": 1, "fields": {}}]))
    before_load = mock.Mock()

    with pytest.raises(backups.RestoreError):
        backups.restore(str(path), ignore_migrations=True, before_load=before_load)

    before_load.assert_not_called()


@pytest.mark.django_db
def test_the_name_to_type_is_the_database_file_name():
    with mock.patch.dict(
        backups.connections["default"].settings_dict, {"NAME": "/srv/blog/db.sqlite3"}
    ):
        assert backups.database_name("default") == "db.sqlite3"

    with mock.patch.dict(
        backups.connections["default"].settings_dict, {"NAME": "travel_magazine"}
    ):
        assert backups.database_name("default") == "travel_magazine"


# Restoring from the Backups page

IMMEDIATE = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}


def dumpdata_upload(name="site.json.gz"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    out = io.StringIO()
    call_command("dumpdata", stdout=out, verbosity=0)
    content = out.getvalue().encode()

    if name.endswith(".gz"):
        content = gzip.compress(content)

    return SimpleUploadedFile(name, content, content_type="application/gzip")


def confirm_data(**extra):
    return {
        "confirm": backups.database_name("default"),
        "password": "x",
        **extra,
    }


@pytest.mark.django_db
def test_the_page_says_who_may_restore(superuser):
    data = client_for(superuser).get("/api/backups").json()

    assert data["restore"]["enabled"] is True
    assert data["restore"]["databases"] == [
        {"alias": "default", "name": backups.database_name("default")}
    ]
    assert data["restore"]["max_upload_size"] == 1024**3
    assert data["restores"] == []


@pytest.mark.django_db
def test_restoring_can_be_turned_off(superuser):
    backup = backups.make_backup()
    client = client_for(superuser)

    with mock.patch.object(
        type(cs_settings.ADMIN_SITE), "has_restore_permission", return_value=False
    ):
        assert client.get("/api/backups").json()["restore"]["enabled"] is False
        assert client.get(f"/api/backups/{backup.pk}/inspect").status_code == 403
        assert (
            client.post("/api/backups/restore", {"backup": backup.pk}).status_code
            == 403
        )


@pytest.mark.django_db
def test_restore_endpoints_are_for_superusers(staff):
    client = client_for(staff)

    assert client.post("/api/backups/restore", {}).status_code == 403
    assert client.post("/api/backups/uploads", {}).status_code == 403


@pytest.mark.django_db
def test_inspect_a_listed_backup(superuser):
    Article.objects.create(title="One")
    backup = backups.make_backup()

    response = client_for(superuser).get(f"/api/backups/{backup.pk}/inspect")

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["manifest"] is True
    assert preview["migrations"]["match"] is True
    assert {"label": "testapp.Article", "count": 1} in preview["models"]
    assert preview["database_name"] == backups.database_name("default")


@pytest.mark.django_db(transaction=True)
@override_settings(TASKS=IMMEDIATE)
def test_restore_a_listed_backup(superuser):
    Article.objects.create(title="Before")
    backup = backups.make_backup()
    Article.objects.all().delete()
    Article.objects.create(title="After")
    client = client_for(superuser)

    response = client.post(
        "/api/backups/restore",
        {"backup": backup.pk, **confirm_data()},
        format="json",
    )

    assert response.status_code == 202, response.json()
    assert list(Article.objects.values_list("title", flat=True)) == ["Before"]
    record = Restore.objects.get()
    assert record.status == Restore.DONE
    assert record.backup == backup
    assert record.rows >= 2
    assert record.created_by == superuser
    safety = record.safety_backup
    assert safety.trigger == Backup.BEFORE_RESTORE
    assert safety.status == Backup.DONE

    data = client.get("/api/backups").json()
    [row] = data["restores"]
    assert row["status"] == "done"
    assert row["safety_backup"] == safety.file.rsplit("/", 1)[-1]


@pytest.mark.django_db(transaction=True)
@override_settings(TASKS=IMMEDIATE)
def test_restore_without_the_safety_backup(superuser):
    backup = backups.make_backup()

    response = client_for(superuser).post(
        "/api/backups/restore",
        {"backup": backup.pk, "safety_backup": False, **confirm_data()},
        format="json",
    )

    assert response.status_code == 202
    assert Restore.objects.get().safety_backup is None
    assert not Backup.objects.filter(trigger=Backup.BEFORE_RESTORE).exists()


@pytest.mark.django_db
def test_restore_asks_for_the_name_and_the_password(superuser):
    backup = backups.make_backup()

    response = client_for(superuser).post(
        "/api/backups/restore",
        {"backup": backup.pk, "confirm": "wrong", "password": "wrong"},
        format="json",
    )

    assert response.status_code == 400
    assert set(response.json()) == {"confirm", "password"}
    assert not Restore.objects.exists()


@pytest.mark.django_db
@override_settings(
    TASKS={"default": {"BACKEND": "django.tasks.backends.dummy.DummyBackend"}}
)
def test_one_restore_at_a_time(superuser):
    backup = backups.make_backup()
    client = client_for(superuser)
    data = {"backup": backup.pk, **confirm_data()}

    assert client.post("/api/backups/restore", data, format="json").status_code == 202
    assert client.post("/api/backups/restore", data, format="json").status_code == 409
    # Back up now waits too.
    assert client.post("/api/backups").status_code == 409


@pytest.mark.django_db(transaction=True)
@override_settings(TASKS=IMMEDIATE)
def test_upload_and_restore_a_dumpdata_file(superuser, fresh_storage):
    Article.objects.create(title="Uploaded", author=superuser)
    upload = dumpdata_upload()
    Article.objects.all().delete()
    client = client_for(superuser)

    response = client.post("/api/backups/uploads", {"file": upload}, format="multipart")

    assert response.status_code == 201, response.json()
    data = response.json()
    preview = data["preview"]
    assert preview["manifest"] is False
    assert preview["migrations"]["checked"] is False
    assert preview["skipped"] > 0
    upload_id = data["upload"]["id"]
    record = Restore.objects.get(pk=upload_id)
    assert record.status == Restore.PENDING
    assert fresh_storage.exists(record.file)
    assert "/uploads/" in record.file

    # The migrations cannot be checked: the dialog's box confirms it.
    response = client.post(
        "/api/backups/restore", {"upload": upload_id, **confirm_data()}, format="json"
    )
    assert response.status_code == 400
    assert "ignore_migrations" in response.json()

    response = client.post(
        "/api/backups/restore",
        {"upload": upload_id, "ignore_migrations": True, **confirm_data()},
        format="json",
    )

    assert response.status_code == 202, response.json()
    assert Article.objects.filter(title="Uploaded").exists()
    record = Restore.objects.get(pk=upload_id)
    assert record.status == Restore.DONE
    assert record.source == Restore.UPLOAD
    assert record.name == "site.json.gz"
    assert not fresh_storage.exists(record.file)


@pytest.mark.django_db
def test_upload_refuses_other_files(superuser):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client = client_for(superuser)
    response = client.post(
        "/api/backups/uploads",
        {"file": SimpleUploadedFile("site.sql", b"DROP TABLE x;")},
        format="multipart",
    )

    assert response.status_code == 400
    assert "JSON fixtures" in response.json()["file"][0]

    response = client.post(
        "/api/backups/uploads",
        {"file": SimpleUploadedFile("site.json", b"{oops")},
        format="multipart",
    )

    assert response.status_code == 400
    assert "not valid JSON" in response.json()["file"][0]
    assert not Restore.objects.exists()


@pytest.mark.django_db
def test_upload_size_limit(superuser):
    with mock.patch.object(cs_settings, "BACKUP_UPLOAD_MAX_SIZE", 10):
        response = client_for(superuser).post(
            "/api/backups/uploads", {"file": dumpdata_upload()}, format="multipart"
        )

    assert response.status_code == 400
    assert "larger than" in response.json()["file"][0]


@pytest.mark.django_db
def test_cancel_an_upload(superuser, fresh_storage):
    client = client_for(superuser)
    upload_id = client.post(
        "/api/backups/uploads", {"file": dumpdata_upload()}, format="multipart"
    ).json()["upload"]["id"]
    name = Restore.objects.get(pk=upload_id).file

    assert client.delete(f"/api/backups/uploads/{upload_id}").status_code == 204
    assert not Restore.objects.exists()
    assert not fresh_storage.exists(name)


@pytest.mark.django_db
def test_old_uploads_are_cleaned_up(superuser, fresh_storage):
    client = client_for(superuser)
    upload_id = client.post(
        "/api/backups/uploads", {"file": dumpdata_upload()}, format="multipart"
    ).json()["upload"]["id"]
    record = Restore.objects.get(pk=upload_id)
    Restore.objects.filter(pk=upload_id).update(
        created_at=timezone.now() - datetime.timedelta(days=2)
    )

    assert backups.clean_uploads() == 1
    assert not fresh_storage.exists(record.file)


@pytest.mark.django_db
def test_restore_command_backs_up_first():
    Article.objects.create(title="Back")
    backups.make_backup()
    Article.objects.all().delete()
    Article.objects.create(title="Current")

    call_command("content_studio_restore", "--latest", "--noinput", verbosity=0)

    safety = Backup.objects.get(trigger=Backup.BEFORE_RESTORE)
    assert safety.status == Backup.DONE
    assert safety.manifest["counts"]["testapp.Article"] == 1


@pytest.mark.django_db
def test_restore_command_without_the_safety_backup():
    backups.make_backup()

    call_command(
        "content_studio_restore",
        "--latest",
        "--noinput",
        "--no-safety-backup",
        verbosity=0,
    )

    assert not Backup.objects.filter(trigger=Backup.BEFORE_RESTORE).exists()


# Huey


@pytest.mark.django_db
def test_huey_runs_the_scheduled_backup():
    from huey import MemoryHuey

    huey = MemoryHuey(f"queue-{uuid.uuid4().hex}", immediate=True)

    with mock.patch.object(backup_huey, "_periodic", None), daily():
        periodic = backup_huey.register_periodic_task(huey)

        name = huey._registry.task_to_string(periodic.task_class)
        assert name == status.RECURRING_KEY
        assert periodic.task_class in huey._registry._periodic_tasks
        assert periodic.task_class().validate_datetime(
            datetime.datetime(2026, 11, 21, 3, 0)
        )

        periodic.call_local()

    assert Backup.objects.get().trigger == Backup.SCHEDULED


def test_huey_without_a_schedule_registers_nothing():
    from huey import MemoryHuey

    huey = MemoryHuey(f"queue-{uuid.uuid4().hex}")

    with mock.patch.object(backup_huey, "_periodic", None):
        assert backup_huey.register_periodic_task(huey) is None


# Checks


def test_clean_settings_pass_the_checks():
    assert backup_errors() == []
    assert backup_storage_errors() == []
    assert backup_warnings() == []


@pytest.mark.parametrize(
    "setting, value, message",
    [
        ("BACKUP_STORAGE", "nowhere", "not in STORAGES"),
        ("BACKUP_DATABASES", ["default", "other"], "'other', not in DATABASES"),
        ("BACKUP_SCHEDULE", "daily", "five fields"),
        ("BACKUP_KEEP", 0, "BACKUP_KEEP"),
        ("BACKUP_EXCLUDE", ["nope.Model"], "'nope.Model'"),
    ],
)
def test_misconfigured_backups_are_errors(setting, value, message):
    with mock.patch.object(cs_settings, setting, value):
        [(check_id, error)] = backup_errors()

    assert check_id == "content_studio.E050"
    assert message in error


def test_backups_in_served_media_are_an_error():
    with mock.patch.object(cs_settings, "BACKUP_STORAGE", "default"):
        [(check_id, error)] = backup_storage_errors()
        assert backup_warnings() == []

    assert check_id == "content_studio.E052"
    assert "SILENCED_SYSTEM_CHECKS" in error


@pytest.mark.parametrize(
    "attributes",
    [{"default_acl": "public-read"}, {"querystring_auth": False}],
)
def test_backups_in_a_public_bucket_are_an_error(attributes):
    storage = type("Bucket", (), attributes)()

    with mock.patch("django.core.files.storage.storages", {"backups": storage}):
        [(check_id, _error)] = backup_storage_errors()

    assert check_id == "content_studio.E052"


def test_a_private_bucket_passes():
    storage = type("Bucket", (), {"default_acl": None, "querystring_auth": True})()

    with mock.patch("django.core.files.storage.storages", {"backups": storage}):
        assert backup_storage_errors() == []


def test_the_storage_error_is_a_system_check_error():
    from django.core import checks

    from content_studio.checks import check_content_studio

    with mock.patch.object(cs_settings, "BACKUP_STORAGE", "default"):
        [message] = check_content_studio()

    assert message.id == "content_studio.E052"
    assert message.level == checks.ERROR


def test_a_schedule_without_huey_is_a_warning():
    with daily():
        [(check_id, warning)] = backup_warnings()

    assert check_id == "content_studio.W028"
    assert "cron" in warning
