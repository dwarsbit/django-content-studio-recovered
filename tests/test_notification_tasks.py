"""The notification digest and pruning as Huey periodic tasks."""

import uuid
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from huey import MemoryHuey

from content_studio import publishing
from content_studio.contrib import status
from content_studio.contrib.huey import HueyAdapter
from content_studio.contrib.status import registry
from content_studio.contrib.status.tasks import apply_registered, serialize_periodic
from content_studio.notifications import tasks
from content_studio.notifications.models import Notification

DIGEST = {
    "ADMIN_SITE": "content_studio.admin.admin_site",
    "NOTIFICATION_EMAIL_DIGEST": True,
    "ADMIN_URL": "https://example.com/admin/",
}


@pytest.fixture
def huey():
    huey = MemoryHuey(f"queue-{uuid.uuid4().hex}", immediate=True)

    with mock.patch.object(tasks, "_registered", None):
        tasks.register_periodic_tasks(huey)
        yield huey


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def clean_registry():
    names = ("_services", "_recurring", "_adapters", "_task_labels", "_errors")
    saved = {name: getattr(registry, name).copy() for name in names}

    for name in names:
        getattr(registry, name).clear()
    yield

    for name in names:
        value = getattr(registry, name)
        value.clear()
        if isinstance(value, dict):
            value.update(saved[name])
        else:
            value.extend(saved[name])


def periodic(huey, path):
    for task_class in huey._registry._periodic_tasks:
        if huey._registry.task_to_string(task_class) == path:
            return task_class
    raise AssertionError(f"{path} is not registered")


def runs_at(task_class, *args):
    return task_class().validate_datetime(datetime(2026, 11, 28, *args))


# Registration


def test_both_tasks_are_registered_with_their_schedules(huey):
    digest = periodic(huey, tasks.DIGEST_TASK)
    pruning = periodic(huey, tasks.PRUNING_TASK)

    assert digest.__name__ == "notification_digest"
    assert runs_at(digest, 9, 10) and runs_at(digest, 23, 10)
    assert not runs_at(digest, 9, 0) and not runs_at(digest, 9, 11)

    assert runs_at(pruning, 4, 30)
    assert not runs_at(pruning, 4, 31) and not runs_at(pruning, 16, 30)


def test_registering_twice_does_nothing(huey):
    assert tasks.register_periodic_tasks(MemoryHuey("other")) is huey
    assert len(huey._registry._periodic_tasks) == 2


def test_without_huey_nothing_is_registered():
    with mock.patch.object(tasks, "_registered", None):
        assert tasks.register_periodic_tasks() is None


# The digest


@pytest.mark.django_db
def test_the_digest_runs_the_command_when_it_is_on(huey):
    with (
        override_settings(CONTENT_STUDIO=DIGEST),
        mock.patch.object(tasks, "call_command") as command,
    ):
        assert tasks.notification_digest() is True

    command.assert_called_once_with(
        "content_studio_send_notification_digest", verbosity=0
    )


@pytest.mark.django_db
def test_the_digest_does_nothing_when_it_is_off(huey):
    with mock.patch.object(tasks, "call_command") as command:
        assert tasks.notification_digest() is False

    command.assert_not_called()


@pytest.mark.django_db
def test_the_huey_task_sends_the_digest(huey):
    with (
        override_settings(CONTENT_STUDIO=DIGEST),
        mock.patch.object(tasks, "call_command") as command,
    ):
        huey.execute(periodic(huey, tasks.DIGEST_TASK)())

    command.assert_called_once()


@pytest.mark.django_db
def test_a_held_lock_skips_the_digest(huey, caplog):
    lock = huey.lock_task(tasks.DIGEST_TASK)

    with (
        override_settings(CONTENT_STUDIO=DIGEST),
        mock.patch.object(tasks, "call_command") as command,
        lock,
    ):
        huey.execute(periodic(huey, tasks.DIGEST_TASK)())

    command.assert_not_called()
    assert "unable to acquire lock" in caplog.text
    assert not lock.is_locked()


# Pruning


@pytest.mark.django_db
def test_the_huey_task_prunes_old_read_notifications(huey):
    anna = User.objects.create_user(username="anna", password="x", is_staff=True)
    old = Notification.objects.create(
        recipient=anna, event="content.updated", read_at=timezone.now()
    )
    fresh = Notification.objects.create(
        recipient=anna, event="content.updated", read_at=timezone.now()
    )
    Notification.objects.filter(pk=old.pk).update(
        updated_at=timezone.now() - timedelta(days=91)
    )

    huey.execute(periodic(huey, tasks.PRUNING_TASK)())

    assert list(Notification.objects.all()) == [fresh]


@pytest.mark.django_db
def test_a_held_lock_skips_pruning(huey):
    with (
        mock.patch.object(tasks, "call_command") as command,
        huey.lock_task(tasks.PRUNING_TASK),
    ):
        huey.execute(periodic(huey, tasks.PRUNING_TASK)())

    command.assert_not_called()


# The last runs on the status page


@pytest.mark.django_db
def test_the_commands_record_their_last_run():
    assert tasks.get_last_run(tasks.PRUNING_TASK) is None

    call_command("content_studio_prune_notifications", verbosity=0)
    with override_settings(CONTENT_STUDIO=DIGEST):
        call_command("content_studio_send_notification_digest", verbosity=0)

    for task in (tasks.PRUNING_TASK, tasks.DIGEST_TASK):
        run = tasks.get_last_run(task)
        assert run.ok and run.message == ""
        assert timezone.now() - run.at < timedelta(minutes=1)


@pytest.mark.django_db
def test_a_failed_run_is_recorded_with_its_error():
    with (
        mock.patch(
            "content_studio.notifications.management.commands."
            "content_studio_prune_notifications.prune",
            side_effect=RuntimeError("database is gone"),
        ),
        pytest.raises(RuntimeError),
    ):
        call_command("content_studio_prune_notifications", verbosity=0)

    run = tasks.get_last_run(tasks.PRUNING_TASK)
    assert not run.ok
    assert run.message == "RuntimeError: database is gone"


def test_the_status_page_shows_each_task_as_one_row(huey, clean_registry):
    tasks.register_status(huey)
    tasks.record_run(tasks.DIGEST_TASK)
    now = timezone.now()

    rows = apply_registered(
        [
            serialize_periodic(row, now)
            for row in HueyAdapter(huey).get_periodic_tasks(None)
        ],
        now,
    )
    by_key = {row["key"]: row for row in rows}

    assert set(by_key) == {tasks.DIGEST_TASK, tasks.PRUNING_TASK}
    digest, pruning = by_key[tasks.DIGEST_TASK], by_key[tasks.PRUNING_TASK]
    assert (digest["title"], digest["schedule"]) == (
        "Notification digest",
        "Every hour at :10",
    )
    assert digest["last_status"] == "SUCCESS" and digest["next_run_at"]
    assert (pruning["title"], pruning["schedule"]) == (
        "Notification pruning",
        "Daily at 04:30 UTC",
    )
    assert pruning["last_run_at"] is None


def test_the_schedule_says_local_time_when_huey_does_not_use_utc(clean_registry):
    tasks.register_status(MemoryHuey("local", utc=False))
    [pruning] = [
        task
        for task in registry.get_recurring_tasks()
        if task.key == tasks.PRUNING_TASK
    ]
    assert str(pruning.schedule) == "Daily at 04:30"


# Scheduled publishing's row, which had the same problem


@pytest.mark.django_db
def test_scheduled_publishing_is_one_row_on_the_status_page(clean_registry):
    huey = MemoryHuey(f"queue-{uuid.uuid4().hex}")

    with (
        mock.patch.object(publishing, "_periodic", None),
        mock.patch.object(
            publishing, "get_publishing_studios", return_value=[object()]
        ),
    ):
        task = publishing.register_periodic_task(huey)
        publishing.register_status()

    path = huey._registry.task_to_string(task.task_class)
    assert [t.key for t in status.registry.get_recurring_tasks()] == [path]
