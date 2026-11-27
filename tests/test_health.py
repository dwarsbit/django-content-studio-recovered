"""
Tests for the health checks (content_studio.health): the endpoints, the
middleware that answers before the Host check, the checks, the worker
heartbeat through the task adapters, content_studio_worker_alive, the
status page's Worker row and the system checks.
"""

import time
import uuid

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import Client, override_settings
from huey import MemoryHuey

from content_studio import checks as system_checks
from content_studio.contrib.huey import HueyAdapter
from content_studio.contrib.status import builtin, registry
from content_studio.dashboard import tasks as task_module
from content_studio.dashboard.tasks import TaskAdapter, TaskRow, TaskStatus
from content_studio.health import (
    HEALTH_PATHS,
    PROBE_PATHS,
    beat,
    checks,
    heartbeat,
)

HEALTH_MIDDLEWARE = "content_studio.health.middleware.HealthCheckMiddleware"


@pytest.fixture
def shared_cache(tmp_path):
    """A cache processes can share, so the worker check is on."""
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": str(tmp_path / "cache"),
            }
        }
    ):
        yield


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """No registered adapters, connected adapters or hidden tasks."""
    monkeypatch.setattr(registry, "_adapters", [])
    monkeypatch.setattr(heartbeat, "_connected", [])
    monkeypatch.setattr(task_module, "_hidden_tasks", set())
    cache.delete(heartbeat.CACHE_KEY)


class Scheduler(TaskAdapter):
    """An adapter whose workers run what it is given."""

    def __init__(self, immediate=False):
        self.immediate = immediate
        self.periodic = {}
        self.startup = {}

    def register_periodic_task(self, key, func, minutes=1, hidden=False):
        self.periodic[key] = (func, minutes, hidden)
        if hidden:
            task_module.hide_task(key)

    def on_worker_startup(self, key, func):
        self.startup[key] = func

    def runs_in_request(self):
        return self.immediate


def stamp(seconds_ago):
    cache.set(heartbeat.CACHE_KEY, time.time() - seconds_ago, None)


@pytest.fixture
def client():
    with override_settings(ROOT_URLCONF="tests.health_urls"):
        yield Client()


# The endpoints


def test_the_paths_are_exported():
    assert PROBE_PATHS == ("/healthz", "/readyz")
    assert HEALTH_PATHS == ("/healthz", "/readyz", "/statusz")


def test_healthz_answers_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_readyz_checks_the_database_and_the_cache(client):
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "cache": "ok"},
    }
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_readyz_is_503_when_the_database_fails(client, monkeypatch):
    def broken(self, *args, **kwargs):
        raise OperationalError("server closed the connection")

    monkeypatch.setattr(
        "django.db.backends.base.base.BaseDatabaseWrapper.cursor", broken
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "error", "cache": "ok"},
    }
    # The error is logged, never shown.
    assert b"server closed" not in response.content


@pytest.mark.django_db
def test_statusz_adds_the_worker_and_off_is_healthy(client):
    response = client.get("/statusz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "cache": "ok", "worker": "off"},
    }


@pytest.mark.django_db
def test_statusz_is_503_when_the_worker_is_stale(client, shared_cache):
    registry.register_task_adapter(Scheduler())
    stamp(seconds_ago=600)

    response = client.get("/statusz")

    assert response.status_code == 503
    assert response.json()["checks"]["worker"] == "error"


@pytest.mark.parametrize("path", HEALTH_PATHS)
@pytest.mark.django_db
def test_only_get_and_head_are_allowed(client, path):
    assert client.post(path).status_code == 405
    assert client.head(path).status_code == 200


# The middleware


@pytest.fixture
def strict_hosts():
    with override_settings(
        ROOT_URLCONF="tests.health_urls",
        ALLOWED_HOSTS=["example.com"],
        MIDDLEWARE=[HEALTH_MIDDLEWARE, *settings.MIDDLEWARE],
    ):
        yield Client(HTTP_HOST="10.0.0.5")


@pytest.mark.django_db
def test_the_middleware_answers_probes_on_any_host(strict_hosts):
    assert strict_hosts.get("/healthz").status_code == 200
    assert strict_hosts.get("/readyz").json()["status"] == "ok"


@pytest.mark.django_db
def test_statusz_and_other_paths_keep_the_host_check(strict_hosts):
    assert strict_hosts.get("/statusz").status_code == 400
    assert strict_hosts.get("/healthz/").status_code == 400


def test_without_the_middleware_an_unknown_host_is_refused():
    with override_settings(
        ROOT_URLCONF="tests.health_urls", ALLOWED_HOSTS=["example.com"]
    ):
        assert Client(HTTP_HOST="10.0.0.5").get("/healthz").status_code == 400


# The checks


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
def test_a_dummy_cache_is_off():
    assert checks.check_cache().status == "off"


def test_a_cache_that_loses_values_is_an_error(monkeypatch):
    monkeypatch.setattr(
        type(cache._connections[cache._alias]), "get", lambda *a, **k: None
    )

    result = checks.check_cache()

    assert result.status == "error"
    assert "read back" in str(result.message)


def test_a_cache_that_raises_is_an_error(monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError("Redis is gone")

    monkeypatch.setattr(type(cache._connections[cache._alias]), "set", broken)

    assert checks.check_cache() == checks.CheckResult(
        "error", "ConnectionError: Redis is gone"
    )


def test_the_worker_is_off_with_a_per_process_cache():
    registry.register_task_adapter(Scheduler())

    result = checks.check_worker()

    assert result.status == "off"
    assert "Local memory" in str(result.message)


def test_the_worker_is_off_without_a_task_backend(shared_cache):
    result = checks.check_worker()

    assert (result.status, str(result.message)) == (
        "off",
        "No task backend connected.",
    )


def test_the_worker_is_off_when_tasks_run_in_the_request(shared_cache):
    registry.register_task_adapter(Scheduler(immediate=True))

    assert checks.check_worker().status == "off"


def test_the_worker_is_off_when_the_backend_cannot_schedule(shared_cache):
    registry.register_task_adapter(TaskAdapter())

    assert checks.check_worker().status == "off"


def test_the_worker_is_an_error_before_its_first_heartbeat(shared_cache):
    registry.register_task_adapter(Scheduler())

    result = checks.check_worker()

    assert result.status == "error"
    assert "No heartbeat from a worker yet" in str(result.message)


def test_a_fresh_heartbeat_is_ok_and_a_stale_one_an_error(shared_cache):
    registry.register_task_adapter(Scheduler())

    stamp(seconds_ago=170)
    assert checks.check_worker().status == "ok"

    stamp(seconds_ago=190)
    result = checks.check_worker()
    assert result.status == "error"
    assert "No heartbeat for 3 minutes" in str(result.message)


def test_the_stale_time_is_a_setting(shared_cache):
    registry.register_task_adapter(Scheduler())
    stamp(seconds_ago=30)

    with override_settings(CONTENT_STUDIO={"HEALTH_WORKER_STALE_AFTER": 20}):
        assert checks.check_worker().status == "error"


def test_calling_beat_turns_the_check_on_without_a_scheduler(shared_cache):
    registry.register_task_adapter(TaskAdapter())
    beat()

    assert checks.check_worker().status == "ok"


# The heartbeat on the adapters


def test_the_heartbeat_is_scheduled_on_an_adapter(shared_cache):
    adapter = Scheduler()

    assert heartbeat.connect(adapter) is True

    func, minutes, hidden = adapter.periodic[heartbeat.HEARTBEAT_TASK]
    assert (minutes, hidden) == (1, True)
    assert adapter.startup[heartbeat.HEARTBEAT_TASK] is func

    func()
    assert heartbeat.get_last_beat() is not None


def test_the_heartbeat_is_not_scheduled_where_it_cannot_be_seen():
    assert heartbeat.connect(Scheduler()) is False


def test_the_heartbeat_is_not_scheduled_when_tasks_run_in_the_request(shared_cache):
    assert heartbeat.connect(Scheduler(immediate=True)) is False


def test_an_adapter_registered_after_startup_gets_the_heartbeat(shared_cache):
    adapter = Scheduler()

    registry.register_task_adapter(adapter)

    assert heartbeat.HEARTBEAT_TASK in adapter.periodic
    # Once per adapter.
    heartbeat.connect_adapters()
    assert heartbeat._connected == [adapter]


def test_a_failing_adapter_does_not_break_startup(shared_cache):
    class Broken(Scheduler):
        def register_periodic_task(self, *args, **kwargs):
            raise RuntimeError("no queue")

    registry.register_task_adapter(Broken())

    assert heartbeat._connected == []


# Huey


@pytest.fixture
def huey(monkeypatch):
    # The runs reset the database connections, as in a worker; not here.
    monkeypatch.setattr(
        "content_studio.contrib.backups.huey.close_old_connections", lambda: None
    )
    return MemoryHuey(f"queue-{uuid.uuid4().hex}")


def test_huey_runs_the_heartbeat_every_minute_and_on_startup(huey, shared_cache):
    adapter = HueyAdapter(huey)

    assert heartbeat.connect(adapter) is True

    task_class = huey._registry._registry[heartbeat.HEARTBEAT_TASK]
    assert task_class in huey._registry._periodic_tasks
    assert heartbeat.HEARTBEAT_TASK in huey._startup

    huey.execute(task_class())
    assert heartbeat.get_last_beat() is not None

    cache.delete(heartbeat.CACHE_KEY)
    huey._startup[heartbeat.HEARTBEAT_TASK]()
    assert heartbeat.get_last_beat() is not None


def test_registering_the_heartbeat_twice_on_one_queue_is_fine(huey, shared_cache):
    heartbeat.connect(HueyAdapter(huey))
    heartbeat.connect(HueyAdapter(huey))

    assert len(huey._registry._periodic_tasks) == 1


def test_huey_in_immediate_mode_gets_no_heartbeat(shared_cache):
    adapter = HueyAdapter(MemoryHuey(f"queue-{uuid.uuid4().hex}", immediate=True))

    assert adapter.runs_in_request() is True
    assert heartbeat.connect(adapter) is False


def test_the_heartbeat_stays_out_of_the_huey_lists(huey, shared_cache, tmp_path):
    import peewee
    from huey.contrib.stats import HueyEvent, HueyStats

    stats = HueyStats(huey, peewee.SqliteDatabase(str(tmp_path / "stats.db")))
    huey._stats = stats
    stats.connect()

    @huey.task()
    def real():
        return 1

    adapter = HueyAdapter(huey)
    heartbeat.connect(adapter)

    try:
        huey.execute(huey._registry._registry[heartbeat.HEARTBEAT_TASK]())
        huey.execute(real.s())
        stats._flush()

        recorded = {event.task for event in HueyEvent.select()}
        # Huey's stats app keeps at most 2000 events: the heartbeat
        # leaves them to the real tasks.
        assert heartbeat.HEARTBEAT_TASK not in recorded
        assert any(task.endswith(".real") for task in recorded)

        assert [row.title for row in adapter.get_recent_tasks(None, 20)] == ["real"]
        assert adapter.get_periodic_tasks(None) == []
    finally:
        stats.close()


def test_hidden_events_recorded_anyway_are_left_out_of_recent_runs(huey, tmp_path):
    import peewee
    from huey.contrib.stats import HueyStats

    stats = HueyStats(huey, peewee.SqliteDatabase(str(tmp_path / "stats.db")))
    huey._stats = stats
    adapter = HueyAdapter(huey)
    adapter.register_periodic_task(
        heartbeat.HEARTBEAT_TASK, heartbeat.beat, hidden=True
    )

    try:
        task = huey._registry._registry[heartbeat.HEARTBEAT_TASK]()
        # Straight to the recorder, as one connected before the filter.
        stats._on_signal("executing", task)
        stats._on_signal("complete", task)
        stats._flush()

        assert adapter.get_recent_tasks(None, 20) == []
    finally:
        stats.close()


# The task lists


def test_hidden_tasks_are_left_out_of_the_task_lists():
    task_module.hide_task("content_studio.health.heartbeat")
    rows = [
        TaskRow("heartbeat", TaskStatus.SUCCESS, key="content_studio.health.heartbeat"),
        TaskRow("sync", TaskStatus.SUCCESS, key="shop.tasks.sync"),
    ]

    assert [row.key for row in task_module.without_hidden(rows)] == ["shop.tasks.sync"]


# The command


def test_worker_alive_passes_with_a_fresh_heartbeat(shared_cache, capsys):
    registry.register_task_adapter(Scheduler())
    stamp(seconds_ago=10)

    call_command("content_studio_worker_alive")

    assert "Worker alive" in capsys.readouterr().out


def test_worker_alive_fails_with_a_stale_heartbeat(shared_cache):
    registry.register_task_adapter(Scheduler())
    stamp(seconds_ago=600)

    with pytest.raises(CommandError, match="No heartbeat for 10 minutes") as error:
        call_command("content_studio_worker_alive")

    assert error.value.returncode == 1


def test_worker_alive_passes_when_there_is_nothing_to_watch(capsys):
    call_command("content_studio_worker_alive")

    assert "Worker check is off" in capsys.readouterr().out


# The status page


def test_the_status_page_worker_row_shows_the_last_heartbeat(shared_cache):
    registry.register_task_adapter(Scheduler())

    stamp(seconds_ago=5)
    result = builtin.check_worker()
    assert (result.status, str(result.detail)) == ("ok", "Last heartbeat just now")

    stamp(seconds_ago=125)
    assert str(builtin.check_worker().detail) == "Last heartbeat 2\xa0minutes ago"

    stamp(seconds_ago=600)
    result = builtin.check_worker()
    assert result.status == "down"
    assert "Is the worker running?" in str(result.message)


def test_the_status_page_worker_row_is_unknown_when_off():
    result = builtin.check_worker()

    assert result.status == "unknown"
    assert "Local memory" in str(result.message)


def test_the_status_page_worker_row_is_down_before_the_first_heartbeat(shared_cache):
    registry.register_task_adapter(Scheduler())

    result = builtin.check_worker()

    assert (result.status, str(result.detail)) == ("down", "No heartbeat")


# System checks


def test_the_middleware_after_security_middleware_warns():
    with override_settings(MIDDLEWARE=[*settings.MIDDLEWARE, HEALTH_MIDDLEWARE]):
        messages = system_checks.check_health_middleware()

    assert [message.id for message in messages] == ["content_studio.W036"]
    assert "SecurityMiddleware" in messages[0].msg


def test_the_middleware_first_does_not_warn():
    with override_settings(MIDDLEWARE=[HEALTH_MIDDLEWARE, *settings.MIDDLEWARE]):
        assert system_checks.check_health_middleware() == []


def test_workers_with_a_per_process_cache_warn():
    registry.register_task_adapter(Scheduler())

    messages = system_checks.check_worker_heartbeat_cache()

    assert [message.id for message in messages] == ["content_studio.W037"]


def test_workers_with_a_shared_cache_do_not_warn(shared_cache):
    registry.register_task_adapter(Scheduler())

    assert system_checks.check_worker_heartbeat_cache() == []


def test_tasks_in_the_request_with_a_per_process_cache_do_not_warn():
    registry.register_task_adapter(Scheduler(immediate=True))

    assert system_checks.check_worker_heartbeat_cache() == []
