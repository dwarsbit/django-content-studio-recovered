"""
Logging: request IDs, one access log line per request, and JSON or plain
log lines.

RequestIdMiddleware gives every request an ID: the X-Request-ID header a
proxy sets, or a new one. It returns the ID in the response's
X-Request-ID header, keeps it for every log line written while the
request runs (RequestIdFilter, get_request_id()) and writes an access log
line on the content_studio.access logger. logging_settings() builds a
LOGGING setting that uses them::

    # settings.py
    from content_studio.logs import logging_settings

    MIDDLEWARE = [
        "content_studio.logs.RequestIdMiddleware",
        "django.middleware.security.SecurityMiddleware",
        ...
    ]
    LOGGING = logging_settings("json" if not DEBUG else "plain")

Nothing here is on until a project adds the middleware or the setting.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

__all__ = [
    "HEADER",
    "JsonFormatter",
    "PlainFormatter",
    "RequestIdFilter",
    "RequestIdMiddleware",
    "get_request_id",
    "logging_settings",
]

_request_id: ContextVar[str | None] = ContextVar(
    "content_studio_request_id", default=None
)

access_logger = logging.getLogger("content_studio.access")

HEADER = "X-Request-ID"

# A forwarded ID is kept only when it is short and plain, so it cannot
# break a log line.
VALID_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")

# The attributes every LogRecord has; anything else came from `extra`.
_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "request_id",
    "taskName",
}


def get_request_id() -> str | None:
    """The ID of the request being handled, or None outside a request
    (or without RequestIdMiddleware)."""
    return _request_id.get()


def quiet_paths() -> tuple[str, ...]:
    """The health check endpoints: their successful requests would bury
    the rest of the access log."""
    from .health import HEALTH_PATHS

    return tuple(HEALTH_PATHS)


class RequestIdFilter(logging.Filter):
    """Sets record.request_id to the ID of the request being handled, or None."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """
    One JSON object per line: time, level, logger, message, the request
    ID, the fields passed with extra=, the exception and the stack.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)

        if request_id:
            entry["request_id"] = request_id

        for key, value in vars(record).items():
            if key not in _RECORD_ATTRS and not key.startswith("_"):
                entry[key] = value

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exception"] = record.exc_text

        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)

        return json.dumps(entry, default=str, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """The format given (by default "LEVEL logger message"), with the
    request ID in brackets when there is one."""

    def __init__(self, fmt=None, datefmt=None, style="%", *args, **kwargs):
        if fmt is None:
            fmt, style = "{levelname} {name} {message}", "{"
        super().__init__(fmt, datefmt, style, *args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        request_id = getattr(record, "request_id", None)
        return f"{line} [{request_id}]" if request_id and "\n" not in line else line


def new_request_id(request) -> str:
    """The forwarded X-Request-ID when it is plain enough, else a new one."""
    forwarded = request.headers.get(HEADER, "")
    return forwarded if VALID_ID.fullmatch(forwarded) else uuid.uuid4().hex


def log_access(request, response, started: float) -> None:
    if request.path_info in quiet_paths() and response.status_code < 400:
        return

    user = getattr(request, "user", None)
    access_logger.info(
        "%s %s %s",
        request.method,
        request.get_full_path(),
        response.status_code,
        extra={
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "user_id": (
                getattr(user, "pk", None)
                if getattr(user, "is_authenticated", False)
                else None
            ),
        },
    )


class RequestIdMiddleware:
    """
    Gives each request an ID for its log lines (and the X-Request-ID
    response header) and writes its access log line. Put it first in
    MIDDLEWARE, so the other middleware's log lines carry the ID too.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)

        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.is_async:
            return self.__acall__(request)

        request_id = new_request_id(request)
        token = _request_id.set(request_id)
        request.request_id = request_id
        started = time.monotonic()

        try:
            response = self.get_response(request)
            response[HEADER] = request_id
            log_access(request, response, started)
            return response
        finally:
            _request_id.reset(token)

    async def __acall__(self, request):
        request_id = new_request_id(request)
        token = _request_id.set(request_id)
        request.request_id = request_id
        started = time.monotonic()

        try:
            response = await self.get_response(request)
            response[HEADER] = request_id
            log_access(request, response, started)
            return response
        finally:
            _request_id.reset(token)


def logging_settings(
    log_format: str = "json", level: str = "INFO", *, access: bool = True
) -> dict[str, Any]:
    """
    A LOGGING setting: every line to the console, as JSON ("json") or
    plain text ("plain"), with the request ID. level is the root logger's
    level; access=False leaves out the access log of RequestIdMiddleware.
    Requests for a host that is not allowed (bots) are logged but never
    reported as errors. Error reports (ERROR_REPORTS) add their handler
    themselves.
    """
    if log_format not in ("json", "plain"):
        raise ValueError(f'log_format must be "json" or "plain", not {log_format!r}.')

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": "content_studio.logs.RequestIdFilter"},
        },
        "formatters": {
            "plain": {"()": "content_studio.logs.PlainFormatter"},
            "json": {"()": "content_studio.logs.JsonFormatter"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": log_format,
                "filters": ["request_id"],
            },
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "content_studio.access": {"level": "INFO" if access else "WARNING"},
            # runserver's own access log; production servers have none.
            "django.server": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            # Requests with a host that is not allowed: bots, never
            # worth an error report.
            "django.security.DisallowedHost": {
                "handlers": ["console"],
                "propagate": False,
            },
            # run_huey adds a handler of its own unless the logger has one.
            "huey": {"handlers": ["console"], "level": "INFO", "propagate": False},
        },
    }
