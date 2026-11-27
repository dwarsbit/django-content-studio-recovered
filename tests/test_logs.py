"""
Logging: the request-ID middleware and its access log, the filter, the
formatters and logging_settings().
"""

import asyncio
import json
import logging
import logging.config
import sys

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from content_studio import logs


def make_middleware(status=200, seen=None):
    def view(request):
        if seen is not None:
            seen.append(logs.get_request_id())
        return HttpResponse(status=status)

    return logs.RequestIdMiddleware(view)


def test_new_request_id_and_header(caplog):
    seen = []
    request = RequestFactory().get("/admin/?page=2")

    with caplog.at_level(logging.INFO, logger="content_studio.access"):
        response = make_middleware(seen=seen)(request)

    request_id = response[logs.HEADER]
    assert len(request_id) == 32
    assert seen == [request_id]
    assert request.request_id == request_id
    # Gone once the request is done.
    assert logs.get_request_id() is None

    [record] = caplog.records
    assert record.getMessage() == "GET /admin/?page=2 200"
    assert record.status == 200
    assert record.path == "/admin/"
    assert record.user_id is None
    assert record.duration_ms >= 0


def test_forwarded_request_id_is_kept_when_plain():
    request = RequestFactory().get("/", HTTP_X_REQUEST_ID="abc-123.def:4")
    assert make_middleware()(request)[logs.HEADER] == "abc-123.def:4"

    request = RequestFactory().get("/", HTTP_X_REQUEST_ID="bad id\nwith newline")
    assert make_middleware()(request)[logs.HEADER] != "bad id\nwith newline"

    request = RequestFactory().get("/", HTTP_X_REQUEST_ID="x" * 200)
    assert len(make_middleware()(request)[logs.HEADER]) == 32


@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/statusz"])
def test_health_checks_are_quiet(path, caplog):
    with caplog.at_level(logging.INFO, logger="content_studio.access"):
        make_middleware()(RequestFactory().get(path))
        assert caplog.records == []

        # A failing health check is logged.
        make_middleware(status=503)(RequestFactory().get(path))
        assert len(caplog.records) == 1


def test_async_middleware():
    seen = []

    async def view(request):
        seen.append(logs.get_request_id())
        return HttpResponse()

    middleware = logs.RequestIdMiddleware(view)
    response = asyncio.run(middleware(RequestFactory().get("/")))

    assert seen == [response[logs.HEADER]]


def test_filter_sets_the_request_id():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hi", (), None)
    token = logs._request_id.set("req-1")

    try:
        assert logs.RequestIdFilter().filter(record)
    finally:
        logs._request_id.reset(token)

    assert record.request_id == "req-1"


def make_record(**extra):
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        "shop", logging.ERROR, __file__, 1, "Order %s failed", ("42",), exc_info
    )
    record.__dict__.update(extra)
    return record


def test_json_formatter():
    line = logs.JsonFormatter().format(make_record(request_id="req-1", order=42))
    entry = json.loads(line)

    assert entry["level"] == "ERROR"
    assert entry["logger"] == "shop"
    assert entry["message"] == "Order 42 failed"
    assert entry["request_id"] == "req-1"
    assert entry["order"] == 42
    assert "ValueError: boom" in entry["exception"]
    assert entry["time"].endswith("+00:00")
    assert "\n" not in line


def test_plain_formatter():
    record = logging.LogRecord("shop", logging.INFO, __file__, 1, "Hi", (), None)
    record.request_id = "req-1"

    assert logs.PlainFormatter().format(record) == "INFO shop Hi [req-1]"


def test_logging_settings_configure():
    config = logs.logging_settings("plain", "WARNING", access=False)

    assert config["handlers"]["console"]["formatter"] == "plain"
    assert config["root"]["level"] == "WARNING"
    assert config["loggers"]["content_studio.access"]["level"] == "WARNING"
    assert logs.logging_settings()["handlers"]["console"]["formatter"] == "json"

    with pytest.raises(ValueError):
        logs.logging_settings("xml")


# Hidden tasks (the worker heartbeat) in Huey's lines


def huey_record(message, *args, name="huey", level=logging.INFO):
    return logging.LogRecord(name, level, __file__, 1, message, args, None)


def test_quiet_tasks_filter_drops_hidden_task_lines():
    from content_studio.dashboard.tasks import hide_task
    from content_studio.health.heartbeat import HEARTBEAT_TASK

    hide_task(HEARTBEAT_TASK)
    quiet = logs.QuietTasksFilter()
    heartbeat = f"{HEARTBEAT_TASK}: 1f2e3d"

    # Huey's three lines for every run.
    assert not quiet.filter(huey_record("Executing %s", heartbeat))
    assert not quiet.filter(huey_record("%s executed in %0.3fs", heartbeat, 0.01))
    assert not quiet.filter(
        huey_record("Enqueueing periodic task %s.", heartbeat, name="huey.consumer")
    )

    # Other tasks, other loggers and warnings go through.
    assert quiet.filter(huey_record("Executing %s", "blog.tasks.publish: 1f2e3d"))
    assert quiet.filter(huey_record("Executing %s", heartbeat, name="shop"))
    assert quiet.filter(
        huey_record("Unhandled exception in task %s.", heartbeat, level=logging.ERROR)
    )


def test_logging_settings_leave_out_hidden_task_lines(capsys):
    from content_studio.dashboard.tasks import hide_task
    from content_studio.health.heartbeat import HEARTBEAT_TASK

    hide_task(HEARTBEAT_TASK)
    previous = logging.root.manager.loggerDict.copy()
    logging.config.dictConfig(logs.logging_settings("plain"))

    try:
        logging.getLogger("huey.consumer").info(
            "Enqueueing periodic task %s.", f"{HEARTBEAT_TASK}: 1f2e3d"
        )
        logging.getLogger("huey").info("Executing %s", "blog.tasks.publish: 4a5b")
    finally:
        logging.config.dictConfig({"version": 1, "disable_existing_loggers": False})
        for name in set(logging.root.manager.loggerDict) - set(previous):
            logging.root.manager.loggerDict.pop(name, None)

    err = capsys.readouterr().err
    assert "blog.tasks.publish" in err
    assert HEARTBEAT_TASK not in err


# Through the test client


@pytest.mark.django_db
@pytest.mark.urls("tests.health_urls")
def test_middleware_in_the_request_cycle(client, settings, caplog):
    settings.MIDDLEWARE = [
        "content_studio.logs.RequestIdMiddleware",
        *settings.MIDDLEWARE,
    ]

    with caplog.at_level(logging.INFO, logger="content_studio.access"):
        response = client.get("/healthz", HTTP_X_REQUEST_ID="proxy-1")
        assert response[logs.HEADER] == "proxy-1"
        assert caplog.records == []

        response = client.get("/no-such-page/", HTTP_X_REQUEST_ID="bad id")

    assert len(response[logs.HEADER]) == 32
    [record] = [r for r in caplog.records if r.name == "content_studio.access"]
    assert record.getMessage() == "GET /no-such-page/ 404"
