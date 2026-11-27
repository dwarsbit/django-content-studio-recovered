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
