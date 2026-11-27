"""
Tests for the status app: registering services, tasks and adapters, the
built-in checks, running and remembering the checks, the task lists and
the endpoints.
"""

import time
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import models as auth_models
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.checks import status_errors
from content_studio.contrib import status
from content_studio.contrib.status import builtin, registry, runner, tasks
from content_studio.dashboard.tasks import (
    TaskAdapter,
    TaskHealth,
    TaskRow,
    TaskStatistic,
    TaskStatus,
)
from content_studio.settings import cs_settings
from content_studio.token_backends.jwt import create_access_token


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.fixture
def clean_registry():
    """Only what the test registers, with the registry restored after."""
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


@pytest.fixture
def superuser(db):
    return auth_models.User.objects.create_user(
        username="root", password="x", is_staff=True, is_superuser=True
    )


@pytest.fixture
def editor(db):
    return auth_models.User.objects.create_user(
        username="editor", password="x", is_staff=True
    )


def by_key(payload):
    return {service["key"]: service for service in payload["services"]}


# Registering


def test_builtin_services_are_registered():
    keys = [service.key for service in registry.get_services()]

    assert keys == [
        "content_studio.database",
        "content_studio.cache",
        "content_studio.media_storage",
        "content_studio.task_queue",
        "content_studio.email",
        "content_studio.migrations",
        # Registered by the backups app, installed in the tests.
        "content_studio.backups",
    ]


def test_a_malformed_key_is_reported(clean_registry):
    status.register_service("Search", "Search", status.ok)
    status.register_recurring_task("backup", "Backup")

    assert registry.get_services() == []
    assert registry.get_recurring_tasks() == []
    assert len(registry.registration_errors()) == 2
    assert [check_id for check_id, _message in status_errors()].count(
        "content_studio.E047"
    ) == 2


def test_registering_twice_is_fine_unless_the_definitions_differ(clean_registry):
    status.register_service("shop.search", "Search", status.ok)
    status.register_service("shop.search", "Search", status.ok)

    assert registry.registration_errors() == []

    status.register_service("shop.search", "Find", status.ok)

    assert len(registry.get_services()) == 1
    assert "registered twice" in registry.registration_errors()[0]


def test_a_check_must_be_callable(clean_registry):
    status.register_service("shop.search", "Search", None)

    assert registry.get_services() == []
    assert "callable" in registry.registration_errors()[0]


# Running the checks


def test_results_carry_status_detail_message_and_group(clean_registry):
    status.register_service(
        "shop.search",
        "Search",
        lambda: status.degraded("Elasticsearch 8", message="Slow."),
        icon="ph-bold ph-magnifying-glass",
        group="Shop",
    )
    status.register_service("shop.payments", "Payments", lambda: None)

    result = runner.check_services()
    services = by_key(result)

    assert result["status"] == "degraded"
    assert services["shop.search"] == {
        "key": "shop.search",
        "label": "Search",
        "group": "Shop",
        "icon": "ph-bold ph-magnifying-glass",
        "url": None,
        "status": "degraded",
        "detail": "Elasticsearch 8",
        "message": "Slow.",
        "duration": mock.ANY,
    }
    # No result is ok.
    assert services["shop.payments"]["status"] == "ok"


def test_the_group_defaults_to_the_app_of_the_check(clean_registry):
    status.register_service("status.cache", "Cache", builtin.check_cache)

    assert runner.check_services()["services"][0]["group"] == "System status"


def test_a_check_that_raises_is_down(clean_registry):
    def check():
        raise ConnectionError("refused")

    status.register_service("shop.search", "Search", check)

    result = runner.check_services()

    assert result["status"] == "down"
    assert result["services"][0]["status"] == "down"
    assert result["services"][0]["message"] == "ConnectionError: refused"


def test_a_check_that_returns_something_else_is_down(clean_registry):
    status.register_service("shop.search", "Search", lambda: "fine")

    assert runner.check_services()["services"][0]["status"] == "down"


def test_a_check_past_its_time_limit_is_down(clean_registry):
    status.register_service(
        "shop.search", "Search", lambda: time.sleep(1), timeout=0.05
    )
    status.register_service("shop.payments", "Payments", status.ok)

    started = time.monotonic()
    result = runner.check_services()
    services = by_key(result)

    assert time.monotonic() - started < 0.9
    assert services["shop.search"]["status"] == "down"
    assert "0.05 seconds" in services["shop.search"]["message"]
    assert services["shop.payments"]["status"] == "ok"


def test_unknown_does_not_change_the_overall_status(clean_registry):
    status.register_service("shop.search", "Search", lambda: status.unknown("Off"))

    assert runner.check_services()["status"] == "ok"


def test_results_are_remembered_until_a_refresh(clean_registry):
    calls = []
    status.register_service("shop.search", "Search", lambda: calls.append(1))

    first = runner.get_status()
    assert runner.get_status() == first
    assert len(calls) == 1

    runner.get_status(force=True)
    assert len(calls) == 2


def test_no_cache_timeout_checks_every_time(clean_registry):
    calls = []
    status.register_service("shop.search", "Search", lambda: calls.append(1))

    with mock.patch.object(cs_settings, "STATUS_CACHE_TIMEOUT", 0):
        runner.get_status()
        runner.get_status()

    assert len(calls) == 2


# Built-in checks


@pytest.mark.django_db
def test_the_database_check_names_the_database():
    result = builtin.check_database()

    assert result.status == "ok"
    assert result.detail.startswith("SQLite 3.")


def test_the_cache_check_stores_and_reads_a_value():
    result = builtin.check_cache()

    assert result.status == "ok"
    assert str(result.detail) == "Local memory"


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
def test_a_dummy_cache_is_not_checked():
    assert builtin.check_cache().status == "unknown"


def test_the_media_storage_check_reaches_the_storage():
    result = builtin.check_media_storage()

    assert result.status == "ok"
    assert str(result.detail) == "File system"


def test_a_slow_storage_is_degraded():
    with mock.patch.object(builtin, "SLOW_STORAGE", -1):
        assert builtin.check_media_storage().status == "degraded"


def test_a_local_email_backend_is_not_checked():
    result = builtin.check_email_backend()

    assert result.status == "unknown"
    assert mail.outbox == []


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.com",
    EMAIL_PORT=587,
)
def test_an_smtp_backend_is_opened_and_closed():
    with (
        mock.patch("django.core.mail.backends.smtp.EmailBackend.open") as open_,
        mock.patch("django.core.mail.backends.smtp.EmailBackend.close") as close,
    ):
        result = builtin.check_email_backend()

    assert result.status == "ok"
    assert result.detail == "SMTP · smtp.example.com:587"
    open_.assert_called_once()
    close.assert_called_once()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="127.0.0.1",
    EMAIL_PORT=1,
    EMAIL_TIMEOUT=1,
)
def test_an_unreachable_smtp_server_is_down(clean_registry):
    status.register_service("content_studio.email", "Email", builtin.check_email)

    assert runner.check_services()["services"][0]["status"] == "down"


@pytest.mark.django_db
def test_the_migrations_check_counts_unapplied_migrations():
    assert builtin.check_migrations().status == "ok"

    with mock.patch(
        "django.db.migrations.executor.MigrationExecutor.migration_plan",
        return_value=[object(), object()],
    ):
        result = builtin.check_migrations()

    assert result.status == "degraded"
    assert str(result.detail) == "2 not applied"


def test_the_task_queue_is_unknown_without_an_adapter(clean_registry):
    assert builtin.check_task_queue().status == "unknown"


class Adapter(TaskAdapter):
    """Two pending, two finished and one periodic task."""

    def __init__(self, now=None):
        self.now = now or timezone.now()

    def get_health(self):
        return TaskHealth("degraded", "Queue · 2 queued", "No worker.")

    def get_statistics(self, request):
        return {
            "queued": TaskStatistic(7),
            "running": TaskStatistic(1),
            "failed": TaskStatistic(3),
        }

    def get_pending_tasks(self, request, limit):
        return [
            TaskRow("send", TaskStatus.QUEUED, key="tests.testapp.tasks.send_mail"),
            TaskRow(
                "resize",
                TaskStatus.RUNNING,
                key="tests.testapp.tasks.ResizeImages",
                last_run_at=self.now,
            ),
        ]

    def get_recent_tasks(self, request, limit):
        return [
            TaskRow(
                "old",
                TaskStatus.SUCCESS,
                description="reports",
                last_run_at=self.now - timedelta(hours=2),
                duration=4,
            ),
            TaskRow(
                "sync",
                TaskStatus.FAILURE,
                key="shop.tasks.sync_orders",
                last_run_at=self.now - timedelta(minutes=5),
                error_message="Boom",
            ),
        ]

    def get_periodic_tasks(self, request):
        return [
            TaskRow(
                "sync",
                TaskStatus.SUCCESS,
                description="Sync the orders.",
                key="shop.tasks.sync_orders",
                last_run_at=self.now - timedelta(minutes=5),
                next_run_at=self.now + timedelta(minutes=10),
            )
        ]


def test_the_task_queue_reports_the_adapter_health(clean_registry):
    status.register_task_adapter(Adapter())

    result = builtin.check_task_queue()

    assert (result.status, result.detail, result.message) == (
        "degraded",
        "Queue · 2 queued",
        "No worker.",
    )


def test_an_adapter_without_health_is_unknown(clean_registry):
    class Plain(TaskAdapter):
        pass

    status.register_task_adapter(Plain())

    assert builtin.check_task_queue().status == "unknown"


# Tasks


def test_tasks_are_named_and_grouped_for_reading(clean_registry):
    status.register_task_adapter(Adapter())
    status.register_task("tests.testapp.tasks.send_mail", "Send the newsletter")

    result = tasks.get_tasks(request=None)

    assert result["connected"] is True
    assert result["errors"] == []
    # Running first; a registered name, or the function's in words.
    assert [(row["title"], row["status"]) for row in result["pending"]] == [
        ("Resize images", "RUNNING"),
        ("Send the newsletter", "QUEUED"),
    ]
    assert result["pending"][0]["source"] == "Testapp"
    # The latest first; rows without a key keep their title and description.
    assert [(row["title"], row["source"]) for row in result["finished"]] == [
        ("Sync orders", ""),
        ("old", "reports"),
    ]
    assert result["finished"][0]["error_message"] == "Boom"
    assert result["counts"] == {"pending": 8, "failed": 3}


def test_counts_come_from_the_rows_without_statistics(clean_registry):
    class NoStatistics(Adapter):
        get_statistics = TaskAdapter.get_statistics

    status.register_task_adapter(NoStatistics())

    assert tasks.get_tasks(request=None)["counts"] == {"pending": 2, "failed": 1}


def test_a_registered_recurring_task_describes_an_adapter_row(clean_registry):
    now = timezone.now()
    status.register_task_adapter(Adapter(now))
    status.register_recurring_task(
        "shop.tasks.sync_orders", "Sync orders with the shop", "Every 15 minutes"
    )

    recurring = tasks.get_tasks(request=None)["recurring"]

    assert recurring == [
        {
            "key": "shop.tasks.sync_orders",
            "title": "Sync orders with the shop",
            "source": "Sync the orders.",
            "schedule": "Every 15 minutes",
            "next_run_at": (now + timedelta(minutes=10)).isoformat(),
            "last_run_at": (now - timedelta(minutes=5)).isoformat(),
            "last_status": "SUCCESS",
            "error_message": None,
            "overdue": False,
        }
    ]


def test_a_registered_recurring_task_shows_without_an_adapter(clean_registry):
    now = timezone.now()
    status.register_recurring_task(
        "backups.database",
        "Database backup",
        "Daily at 03:00",
        get_last_run=lambda: status.Run(now - timedelta(days=2), False, "Disk full"),
        get_next_run=lambda: now - timedelta(hours=9),
        group="Backups",
    )
    status.register_recurring_task(
        "backups.media", "Media backup", get_last_run=lambda: now
    )

    result = tasks.get_tasks(request=None)
    database, media = result["recurring"]

    assert result["connected"] is False
    assert database["source"] == "Backups"
    assert database["last_status"] == "FAILURE"
    assert database["error_message"] == "Disk full"
    assert database["overdue"] is True
    assert media["last_status"] == "SUCCESS"
    assert media["overdue"] is False


def test_a_failing_adapter_is_reported_and_the_rest_shows(clean_registry):
    class Broken(TaskAdapter):
        def get_recent_tasks(self, request, limit):
            raise ConnectionError("redis is gone")

    status.register_task_adapter(Broken())
    status.register_task_adapter(Adapter())

    result = tasks.get_tasks(request=None)

    assert result["errors"] == ["Broken: ConnectionError: redis is gone"]
    assert len(result["finished"]) == 2


def test_a_failing_recurring_task_reports_its_error(clean_registry):
    def last_run():
        raise RuntimeError("no bucket")

    status.register_recurring_task("backups.database", "Backup", get_last_run=last_run)

    row = tasks.get_tasks(request=None)["recurring"][0]

    assert row["error_message"] == "RuntimeError: no bucket"


def test_humanize():
    assert tasks.humanize("sync_orders") == "Sync orders"
    assert tasks.humanize("SyncOrders") == "Sync orders"


# Endpoints


def test_the_status_page_is_for_superusers(clean_registry, superuser, editor):
    status.register_service("shop.search", "Search", lambda: status.ok("Fine"))

    for path in ("", "/summary", "/tasks"):
        assert client_for(editor).get(f"/api/status{path}").status_code == 403
        assert APIClient().get(f"/api/status{path}").status_code in (401, 403)
        assert client_for(superuser).get(f"/api/status{path}").status_code == 200

    assert client_for(editor).post("/api/status/refresh").status_code == 403


def test_the_site_decides_who_may_open_the_page(clean_registry, editor):
    with mock.patch.object(
        cs_settings.ADMIN_SITE, "has_status_permission", lambda request: True
    ):
        assert client_for(editor).get("/api/status").status_code == 200
        discover = client_for(editor).get("/api/discover").json()

    assert discover["status"] == {"enabled": True}


def test_discover_tells_whether_the_user_sees_the_page(superuser, editor):
    assert client_for(superuser).get("/api/discover").json()["status"] == {
        "enabled": True
    }
    assert client_for(editor).get("/api/discover").json()["status"] == {
        "enabled": False
    }


def test_the_endpoints_serve_the_services_and_the_summary(clean_registry, superuser):
    calls = []

    def check():
        calls.append(1)
        return status.down("Elasticsearch", message="No answer.")

    status.register_service("shop.search", "Search", check)
    client = client_for(superuser)

    data = client.get("/api/status").json()

    assert data["status"] == "down"
    assert data["services"][0]["message"] == "No answer."
    assert client.get("/api/status/summary").json() == {
        "status": "down",
        "checked_at": data["checked_at"],
    }
    assert len(calls) == 1

    assert client.post("/api/status/refresh").json()["status"] == "down"
    assert len(calls) == 2


def test_the_builtin_checks_run_through_the_endpoint(superuser):
    data = client_for(superuser).get("/api/status").json()
    services = by_key(data)

    assert services["content_studio.database"]["status"] == "ok"
    assert services["content_studio.migrations"]["status"] == "ok"
    assert services["content_studio.database"]["group"] == "Content Studio"
    assert data["status"] == "ok"


def test_the_tasks_endpoint(clean_registry, superuser):
    status.register_task_adapter(Adapter())

    data = client_for(superuser).get("/api/status/tasks").json()

    assert data["connected"] is True
    assert len(data["pending"]) == 2
    assert len(data["recurring"]) == 1


def test_huey_is_used_when_installed_and_nothing_is_registered(
    clean_registry, monkeypatch
):
    monkeypatch.setattr(tasks.apps, "is_installed", lambda name: name == tasks.HUEY_APP)
    monkeypatch.setattr(tasks, "_huey_adapter", None)

    assert [type(adapter).__name__ for adapter in tasks.get_adapters()] == [
        "HueyAdapter"
    ]

    mine = Adapter()
    status.register_task_adapter(mine)

    assert tasks.get_adapters() == [mine]
