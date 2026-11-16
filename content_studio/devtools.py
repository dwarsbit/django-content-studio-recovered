"""
Developer tools: the warnings and errors a developer should act on,
gathered while DEBUG is on and shown in the admin behind a floating
button.

Issues come from system checks, from Content Studio's loggers (and any
in DEVTOOLS_LOGGERS), from unhandled exceptions in the admin API, from
requests that run many similar queries, and from code that calls
report(). The admin API's requests are recorded with their timing and
queries. Everything is kept in memory, per process, and only while
developer tools are on: with DEBUG off nothing is recorded, the
endpoint answers 404 and no header is added.
"""

import functools
import itertools
import logging
import platform
import sys
import threading
import time
import traceback
from collections import OrderedDict, deque
from contextlib import ExitStack

import django
from django.conf import settings
from django.core import checks
from django.db import connections
from django.utils import timezone

from .settings import cs_settings

DOCS_URL = "https://djangocontentstudio.org/docs"

# How many issues and requests are kept; the oldest go first.
MAX_ISSUES = 200
MAX_REQUESTS = 50

# A request that runs more alike queries than this is reported.
SIMILAR_QUERIES = 10

# Queries kept per recorded request: the slowest and the most repeated.
QUERIES_PER_REQUEST = 5

# The response header that tells the admin the issues changed.
HEADER = "X-Content-Studio-Devtools"

LEVELS = ("error", "warning", "info")


def is_enabled() -> bool:
    """Developer tools are on while DEBUG is on, unless DEVTOOLS is False."""
    return bool(settings.DEBUG) and cs_settings.DEVTOOLS is not False


def now() -> str:
    return timezone.now().isoformat()


class Store:
    """The issues and requests of this process."""

    def __init__(self):
        self.lock = threading.Lock()
        self.issues: OrderedDict[str, dict] = OrderedDict()
        self.requests: deque[dict] = deque(maxlen=MAX_REQUESTS)
        self.ids = itertools.count(1)
        # Bumped on every change to the issues: the admin refetches when
        # the header shows a newer number.
        self.seq = 0
        self.checked = False

    def add(self, key: str, issue: dict):
        with self.lock:
            existing = self.issues.pop(key, None)

            if existing:
                issue = {
                    **issue,
                    "id": existing["id"],
                    "count": existing["count"] + 1,
                    "first_seen": existing["first_seen"],
                }
            else:
                issue = {
                    **issue,
                    "id": str(next(self.ids)),
                    "count": 1,
                    "first_seen": issue["last_seen"],
                }

            self.issues[key] = issue

            while len(self.issues) > MAX_ISSUES:
                self.issues.popitem(last=False)

            self.seq += 1

    def remove(self, source: str | None = None):
        """Removes the issues of one source, or all of them."""
        with self.lock:
            for key in [
                key
                for key, issue in self.issues.items()
                if source is None or issue["source"] == source
            ]:
                del self.issues[key]

            self.seq += 1

    def add_request(self, record: dict):
        with self.lock:
            record["id"] = str(next(self.ids))
            self.requests.append(record)

    def clear_requests(self, user_id):
        with self.lock:
            kept = [r for r in self.requests if r["user"] != user_id]
            self.requests.clear()
            self.requests.extend(kept)

    def get_issues(self) -> list[dict]:
        with self.lock:
            # Newest first.
            return [dict(issue) for issue in reversed(self.issues.values())]

    def get_requests(self, user_id) -> list[dict]:
        with self.lock:
            return [
                {key: value for key, value in record.items() if key != "user"}
                for record in reversed(self.requests)
                if record["user"] == user_id
            ]

    def reset(self):
        """Forgets everything (for tests)."""
        with self.lock:
            self.issues.clear()
            self.requests.clear()
            self.seq += 1
            self.checked = False


store = Store()


def report(
    level: str,
    message: str,
    *,
    code: str = "",
    title: str = "",
    hint: str = "",
    snippet: str = "",
    docs: str = "",
    studio: str = "",
    key: str | None = None,
    source: str = "report",
    stack: str = "",
    request=None,
):
    """
    Shows an issue in the developer tools while they are on; does
    nothing otherwise, so it is safe to call anywhere.

    level is "error", "warning" or "info". Issues with the same key (by
    default the code and the message) are shown once, with a count. hint
    is a suggestion, snippet code to copy, docs a link to read more.
    """
    if not is_enabled():
        return

    if level not in LEVELS:
        level = "warning"

    store.add(
        key or f"{code}:{message}",
        {
            "level": level,
            "code": code,
            "title": str(title),
            "message": str(message),
            "hint": str(hint),
            "snippet": snippet,
            "docs": docs,
            "studio": studio,
            "source": source,
            "stack": stack,
            "method": getattr(request, "method", "") or "",
            "path": api_path(request) if request is not None else "",
            "last_seen": now(),
        },
    )


class DevtoolsLogHandler(logging.Handler):
    """
    Turns warnings and errors of Content Studio's loggers into issues.
    A record's extra={"devtools": {...}} adds a title, hint, snippet,
    docs link, code or key; extra={"devtools": False} leaves it out.
    """

    def emit(self, record):
        details = getattr(record, "devtools", None)

        if details is False or not is_enabled():
            return

        try:
            details = details if isinstance(details, dict) else {}
            stack = ""

            if record.exc_info:
                stack = "".join(traceback.format_exception(*record.exc_info))

            report(
                "error" if record.levelno >= logging.ERROR else "warning",
                record.getMessage(),
                code=details.get("code", record.name),
                title=details.get("title", ""),
                hint=details.get("hint", ""),
                snippet=details.get("snippet", ""),
                docs=details.get("docs", ""),
                studio=details.get("studio", ""),
                # The same message with other values (another file,
                # another studio) counts as the same issue.
                key=details.get("key", f"log:{record.name}:{record.msg}"),
                source="log",
                stack=stack,
            )
        except Exception:  # noqa: BLE001 -- logging must never raise
            self.handleError(record)


log_handler = DevtoolsLogHandler(level=logging.WARNING)


def install_log_handler():
    """Attaches the handler to Content Studio's loggers and DEVTOOLS_LOGGERS."""
    extra = cs_settings.DEVTOOLS_LOGGERS
    # A wrong setting is reported by system check E049.
    extra = (
        [name for name in extra if isinstance(name, str) and name]
        if isinstance(extra, (list, tuple))
        else []
    )
    names = ["content_studio", *extra]

    for name in names:
        logger = logging.getLogger(name)

        if log_handler not in logger.handlers:
            logger.addHandler(log_handler)


def run_system_checks():
    """
    Runs the system checks and shows their warnings and errors, in place
    of those of an earlier run. Silenced checks stay silent.
    """
    messages = [
        message
        for message in checks.run_checks(include_deployment_checks=False)
        if message.level >= checks.WARNING and not message.is_silenced()
    ]

    store.remove("check")

    for message in messages:
        obj = message.obj

        if obj is not None and not isinstance(obj, str):
            obj = getattr(obj, "__name__", None) or str(obj)

        report(
            "error" if message.level >= checks.ERROR else "warning",
            message.msg,
            code=message.id or "",
            title=f"System check {message.id}" if message.id else "System check",
            hint=message.hint or "",
            docs=f"{DOCS_URL}/deployment#system-checks",
            studio=obj or "",
            key=f"check:{message.id}:{obj}:{message.msg}",
            source="check",
        )

    store.checked = True


def ensure_system_checks():
    """Runs the system checks once per process."""
    if not store.checked:
        run_system_checks()


def normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


class QueryRecorder:
    """Records the queries of one request, on every database."""

    def __init__(self):
        self.queries: list[tuple[str, float]] = []

    def __call__(self, execute, sql, params, many, context):
        start = time.perf_counter()

        try:
            return execute(sql, params, many, context)
        finally:
            self.queries.append(
                (normalize_sql(str(sql)), (time.perf_counter() - start) * 1000)
            )

    def summary(self) -> dict:
        counts: dict[str, int] = {}

        for sql, _ms in self.queries:
            counts[sql] = counts.get(sql, 0) + 1

        slowest = sorted(self.queries, key=lambda query: query[1], reverse=True)
        repeated = sorted(
            ((sql, count) for sql, count in counts.items() if count > 1),
            key=lambda item: item[1],
            reverse=True,
        )

        return {
            "queries": len(self.queries),
            "query_ms": round(sum(ms for _sql, ms in self.queries), 1),
            "slowest": [
                {"sql": sql, "ms": round(ms, 1)}
                for sql, ms in slowest[:QUERIES_PER_REQUEST]
            ],
            "similar": [
                {"sql": sql, "count": count}
                for sql, count in repeated[:QUERIES_PER_REQUEST]
            ],
        }


def api_path(request) -> str:
    """The request's path from the admin API's root, with its query."""
    path = request.get_full_path()
    marker = "/api/"
    index = path.find(marker)

    return path[index + len(marker) :] if index >= 0 else path


def is_devtools_request(request) -> bool:
    return "/api/devtools" in request.path


def record(view):
    """
    Wraps an admin API view: while developer tools are on, its requests
    are recorded with their queries, an unhandled exception becomes an
    issue, and the response carries the issues' sequence number.
    """

    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_enabled():
            return view(request, *args, **kwargs)

        if is_devtools_request(request):
            response = view(request, *args, **kwargs)
            response[HEADER] = str(store.seq)
            return response

        recorder = QueryRecorder()
        start = time.perf_counter()
        status = 500

        try:
            with ExitStack() as stack:
                for connection in connections.all():
                    stack.enter_context(connection.execute_wrapper(recorder))

                response = view(request, *args, **kwargs)

            status = response.status_code
        except Exception as error:
            report(
                "error",
                f"{type(error).__name__}: {error}",
                code="500",
                title=f"{request.method} request failed",
                stack=traceback.format_exc(),
                key=f"exception:{type(error).__name__}:{request.method}:{request.path}",
                source="server",
                request=request,
            )
            raise
        finally:
            store_request(request, status, start, recorder)

        response[HEADER] = str(store.seq)

        return response

    return wrapped


def store_request(request, status, start, recorder):
    try:
        summary = recorder.summary()
        user = getattr(request, "user", None)
        user_id = getattr(user, "pk", None)
        store.add_request(
            {
                "method": request.method,
                "path": api_path(request),
                "status": status,
                "ms": round((time.perf_counter() - start) * 1000, 1),
                "time": now(),
                "user": user_id,
                **summary,
            }
        )

        similar = summary["similar"][0] if summary["similar"] else None

        if similar and similar["count"] > SIMILAR_QUERIES:
            match = getattr(request, "resolver_match", None)
            route = getattr(match, "route", "") or request.path
            report(
                "warning",
                f"{request.method} {api_path(request)} ran {similar['count']} "
                "alike queries.",
                code="similar_queries",
                title="Many similar queries",
                hint="One query per related object usually means a missing "
                "select_related or prefetch_related in the studio's "
                "get_queryset.",
                snippet=f"{similar['sql']}   × {similar['count']}",
                docs=f"{DOCS_URL}/developer-tools#many-similar-queries",
                key=f"similar_queries:{request.method}:{route}",
                source="server",
                request=request,
            )
    except Exception:  # noqa: BLE001 -- recording must never break a request
        logging.getLogger(__name__).debug(
            "Could not record a request.", exc_info=True, extra={"devtools": False}
        )


def wrap_urlpatterns(urlpatterns):
    """Records the requests of the admin API's URL patterns."""
    for pattern in urlpatterns:
        if hasattr(pattern, "url_patterns"):
            # An included resolver: wrap what it includes.
            wrap_urlpatterns(pattern.url_patterns)
        elif str(pattern.pattern).lstrip("^").startswith("api"):
            pattern.callback = record(pattern.callback)

    return urlpatterns


def get_database_info(connection) -> str:
    name = connection.display_name

    try:
        version = connection.get_database_version()
    except Exception:  # noqa: BLE001 -- the version is decorative
        return name

    return f"{name} {'.'.join(str(part) for part in version)}"


def class_name(path) -> str:
    if not path:
        return ""

    return str(path).rsplit(".", 1)[-1]


def get_info(site) -> dict:
    from . import __version__

    tasks = getattr(settings, "TASKS", None) or {}
    task_backend = (tasks.get("default") or {}).get("BACKEND") if tasks else None
    caches = getattr(settings, "CACHES", None) or {}
    token_backend = site.token_backend.active_backend

    return {
        "environment": [
            {"label": "Content Studio", "value": __version__},
            {"label": "Django", "value": django.get_version()},
            {"label": "Python", "value": platform.python_version()},
            {
                "label": "Database",
                "value": get_database_info(connections["default"]),
            },
            {
                "label": "Cache",
                "value": class_name(
                    (caches.get("default") or {}).get(
                        "BACKEND", "django.core.cache.backends.locmem.LocMemCache"
                    )
                ),
                "code": True,
            },
            {
                "label": "Tasks",
                "value": class_name(task_backend) or "None",
                "code": True,
            },
            {
                "label": "Login",
                "value": type(token_backend).__name__,
                "code": True,
            },
            {
                "label": "Language, time zone",
                "value": f"{settings.LANGUAGE_CODE}, {settings.TIME_ZONE}",
            },
        ],
        "studios": {
            model._meta.label_lower: {
                "studio": type(studio).__name__,
                "module": type(studio).__module__,
                "list_count": getattr(studio, "list_count", "exact"),
                "list_per_page": getattr(studio, "list_per_page", None),
            }
            for model, studio in site._registry.items()
        },
        "platform": sys.platform,
    }
