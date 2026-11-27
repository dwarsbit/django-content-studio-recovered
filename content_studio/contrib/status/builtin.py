"""
The services the status page checks out of the box: the databases, the
cache, the media storage, the task queue, outgoing email and the
migrations.
"""

import time
import uuid
import warnings

from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .registry import (
    ServiceResult,
    ServiceStatus,
    degraded,
    down,
    ok,
    register_service,
    unknown,
)

GROUP = _("Content Studio")

# Seconds after which an answer counts as slow.
SLOW_DATABASE = 1
SLOW_STORAGE = 2

CACHE_NAMES = {
    "RedisCache": "Redis",
    "PyMemcacheCache": "Memcached",
    "PyLibMCCache": "Memcached",
    "DatabaseCache": _("Database cache"),
    "FileBasedCache": _("File cache"),
    "LocMemCache": _("Local memory"),
}

STORAGE_NAMES = {
    "FileSystemStorage": _("File system"),
    "InMemoryStorage": _("Memory"),
}

# Email backends that send nothing.
LOCAL_EMAIL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend": _("Console"),
    "django.core.mail.backends.locmem.EmailBackend": _("Local memory"),
    "django.core.mail.backends.filebased.EmailBackend": _("Files"),
    "django.core.mail.backends.dummy.EmailBackend": _("Dummy"),
}


def slow_message(elapsed: float):
    return _("Answered in %(seconds).1f seconds.") % {"seconds": elapsed}


def check_database(alias: str = "default") -> ServiceResult:
    from django.db import connections

    connection = connections[alias]
    started = time.monotonic()
    connection.ensure_connection()

    if not connection.is_usable():
        return down(connection.display_name, _("The connection is not usable."))

    elapsed = time.monotonic() - started
    detail = connection.display_name

    try:
        version = ".".join(str(part) for part in connection.get_database_version())
        detail = f"{detail} {version}"
    except Exception:
        pass

    if elapsed > SLOW_DATABASE:
        return degraded(detail, slow_message(elapsed))
    return ok(detail)


def check_cache() -> ServiceResult:
    from django.core.cache import DEFAULT_CACHE_ALIAS, cache, caches
    from django.core.cache.backends.dummy import DummyCache

    backend = caches[DEFAULT_CACHE_ALIAS]
    name = type(backend).__name__
    detail = CACHE_NAMES.get(name, name)

    if isinstance(backend, DummyCache):
        return unknown(_("Dummy cache"), _("Nothing is cached."))

    key = f"content_studio.status.check.{uuid.uuid4().hex}"
    cache.set(key, "1", 30)
    stored = cache.get(key)
    cache.delete(key)

    if stored != "1":
        return down(detail, _("A value that was stored could not be read back."))
    return ok(detail)


def check_media_storage() -> ServiceResult:
    from django.core.files.storage import default_storage, storages

    backend = storages["default"]
    name = type(backend).__name__
    detail = STORAGE_NAMES.get(name, name)
    started = time.monotonic()
    default_storage.exists("content-studio-status-check")
    elapsed = time.monotonic() - started

    if elapsed > SLOW_STORAGE:
        return degraded(detail, slow_message(elapsed))
    return ok(detail)


def check_task_queue() -> ServiceResult:
    from .tasks import get_adapters

    adapters = get_adapters()

    if not adapters:
        return unknown(_("No task backend connected"))

    order = [
        ServiceStatus.UNKNOWN,
        ServiceStatus.OK,
        ServiceStatus.DEGRADED,
        ServiceStatus.DOWN,
    ]
    worst = None

    for adapter in adapters:
        if adapter.implements("get_health"):
            health = adapter.get_health()
            result = ServiceResult(health.status, health.detail, health.message)
        else:
            result = unknown(type(adapter).__name__)

        if worst is None or order.index(result.status) > order.index(worst.status):
            worst = result

    return worst


def get_email_connection():
    """The default email connection, whichever way Django configures it."""
    from django.core import mail

    mailers = getattr(mail, "mailers", None)

    if mailers is not None:
        # Django 6.1 and later: MAILERS, or the settings it replaces.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return mailers.default

    return mail.get_connection()


def check_email() -> ServiceResult:
    result = check_email_backend()

    if not apps.is_installed("content_studio.contrib.email_activity"):
        return result

    # The emails logged in the last day: a count, and Degraded on failures.
    from ..email_activity.log import status_summary

    sent, message = status_summary()
    detail = " · ".join(part for part in (str(result.detail), sent) if part)

    if message and result.status != ServiceStatus.DOWN:
        return degraded(detail, message)

    return ServiceResult(result.status, detail, result.message)


def check_email_backend() -> ServiceResult:
    from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

    connection = get_email_connection()

    if apps.is_installed("content_studio.contrib.email_activity"):
        from ..email_activity.backends import EmailBackend as LoggingBackend

        if isinstance(connection, LoggingBackend):
            # The backend the logging backend delivers with.
            connection = connection.delivery

    path = f"{type(connection).__module__}.{type(connection).__name__}"
    local = LOCAL_EMAIL_BACKENDS.get(path)

    if local is not None:
        return unknown(
            _("%(backend)s backend") % {"backend": local},
            _("Emails are not sent from this backend."),
        )

    if not isinstance(connection, SMTPBackend):
        # Only an SMTP server can be reached without sending an email.
        return unknown(type(connection).__module__.rsplit(".", 1)[0])

    detail = f"SMTP · {connection.host}:{connection.port}"
    connection.fail_silently = False

    try:
        connection.open()
    finally:
        connection.close()

    return ok(detail)


def check_migrations() -> ServiceResult:
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())

    if plan:
        return degraded(
            _("%(count)s not applied") % {"count": len(plan)},
            _("Run manage.py migrate."),
        )
    return ok(_("Up to date"))


def register_builtin_services():
    for alias in settings.DATABASES:
        default = alias == "default"
        slug = "".join(c if c.isalnum() else "_" for c in alias.lower())

        def check(alias=alias):
            return check_database(alias)

        register_service(
            "content_studio.database" if default else f"content_studio.database.{slug}",
            _("Database") if default else _("Database (%(alias)s)") % {"alias": alias},
            check,
            icon="ph-bold ph-database",
            group=GROUP,
        )

    register_service(
        "content_studio.cache",
        _("Cache"),
        check_cache,
        icon="ph-bold ph-lightning",
        group=GROUP,
    )
    register_service(
        "content_studio.media_storage",
        _("Media storage"),
        check_media_storage,
        icon="ph-bold ph-hard-drives",
        group=GROUP,
    )
    register_service(
        "content_studio.task_queue",
        _("Task queue"),
        check_task_queue,
        icon="ph-bold ph-queue",
        group=GROUP,
    )
    register_service(
        "content_studio.email",
        _("Email"),
        check_email,
        icon="ph-bold ph-envelope-simple",
        group=GROUP,
        timeout=10,
        # The Email activity page, with the optional app installed.
        url=(
            "email-activity"
            if apps.is_installed("content_studio.contrib.email_activity")
            else None
        ),
    )
    register_service(
        "content_studio.migrations",
        _("Migrations"),
        check_migrations,
        icon="ph-bold ph-git-branch",
        group=GROUP,
    )
