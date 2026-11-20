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

from content_studio.checks import backup_errors, backup_warnings
from content_studio.contrib.backups import backup as backups
from content_studio.contrib.backups import huey as backup_huey
from content_studio.contrib.backups import schedule, status
from content_studio.contrib.backups.models import Backup
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

    with fresh_storage.open(backups.manifest_name(backup.file), "rb") as file:
        manifest = json.loads(file.read())

    assert manifest == backup.manifest
    assert manifest["database"] == "default"
    assert manifest["engine"] == "sqlite"
    assert manifest["counts"]["testapp.Article"] == 1
    assert "0001_initial" in manifest["migrations"]["auth"]


@pytest.mark.django_db
def test_backup_leaves_out_backup_exclude():
    Article.objects.create(title="Left out")

    with mock.patch.object(cs_settings, "BACKUP_EXCLUDE", ["testapp.Article"]):
        backup = backups.make_backup()

    objects = read_fixture(storages["backups"], backup.file)

    assert "testapp.article" not in {item["model"] for item in objects}
    assert "testapp.Article" not in backup.manifest["counts"]


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


def test_backups_in_served_media_are_a_warning():
    with mock.patch.object(cs_settings, "BACKUP_STORAGE", "default"):
        [(check_id, warning)] = backup_warnings()

    assert check_id == "content_studio.W027"


def test_a_schedule_without_huey_is_a_warning():
    with daily():
        [(check_id, warning)] = backup_warnings()

    assert check_id == "content_studio.W028"
    assert "cron" in warning
