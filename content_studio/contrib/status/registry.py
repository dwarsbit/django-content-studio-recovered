"""
What the status page shows: the services, task adapters, recurring tasks
and task names that apps register.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Optional, Union

from ..._types import StrOrPromise

# Lowercase dotted words, like "shop.search".
KEY_PATTERN = re.compile(r"^[a-z0-9_-]+(\.[a-z0-9_-]+)+$")

# Seconds a check may take before its service shows as down.
DEFAULT_TIMEOUT = 5


class ServiceStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    # Not checked: there is nothing to check, or no way to.
    UNKNOWN = "unknown"


@dataclass
class ServiceResult:
    """
    What a service's check returns: its status, a short line about the
    service (such as "PostgreSQL 16.4") and, when something is wrong, a
    message saying what.
    """

    status: str = ServiceStatus.OK
    detail: Any = ""
    message: Any = ""


def ok(detail: StrOrPromise = "", message: StrOrPromise = "") -> ServiceResult:
    return ServiceResult(ServiceStatus.OK, detail, message)


def degraded(detail: StrOrPromise = "", message: StrOrPromise = "") -> ServiceResult:
    return ServiceResult(ServiceStatus.DEGRADED, detail, message)


def down(detail: StrOrPromise = "", message: StrOrPromise = "") -> ServiceResult:
    return ServiceResult(ServiceStatus.DOWN, detail, message)


def unknown(detail: StrOrPromise = "", message: StrOrPromise = "") -> ServiceResult:
    return ServiceResult(ServiceStatus.UNKNOWN, detail, message)


@dataclass(frozen=True)
class Service:
    key: str
    label: Any
    check: Callable[[], Optional[ServiceResult]]
    icon: Optional[str] = None
    group: Any = None
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class Run:
    """The last run of a recurring task, when more than its time is known."""

    at: Optional[datetime] = None
    ok: bool = True
    message: Any = ""


@dataclass(frozen=True)
class RecurringTask:
    key: str
    label: Any
    schedule: Any = ""
    get_last_run: Optional[Callable[[], Union[datetime, Run, None]]] = None
    get_next_run: Optional[Callable[[], Optional[datetime]]] = None
    group: Any = None


# Registered services and recurring tasks by key, in registration order.
_services: dict[str, Service] = {}
_recurring: dict[str, RecurringTask] = {}
# Task adapters, in registration order.
_adapters: list[Any] = []
# Readable names of tasks, by dotted path.
_task_labels: dict[str, Any] = {}
# Problems found while registering, reported by system check E047.
_errors: list[str] = []


def _valid_key(kind: str, key) -> bool:
    if isinstance(key, str) and KEY_PATTERN.match(key):
        return True
    _errors.append(
        f"{kind} key {key!r} must be lowercase dotted words, " f'like "shop.search".'
    )
    return False


def register_service(
    key: str,
    label: StrOrPromise,
    check: Callable[[], Optional[ServiceResult]],
    icon: Optional[str] = None,
    group: Optional[StrOrPromise] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """
    Add a service to the status page. key is lowercase dotted words
    starting with the app, like "shop.search"; label names the service.

    check is called without arguments when the page asks, and returns
    status.ok(), status.degraded(), status.down() or status.unknown(),
    each with a short detail line and an optional message. Returning
    None counts as ok. A check that raises, or takes longer than
    `timeout` seconds, shows the service as down.

    icon is a Phosphor icon class, such as "ph-bold ph-database". group
    is the heading the service is listed under; by default the name of
    the app the check is defined in.

    Registering a key twice with different definitions is reported by
    system check content_studio.E047.
    """
    service = Service(
        key=key, label=label, check=check, icon=icon, group=group, timeout=timeout
    )

    if not _valid_key("Status service", key):
        return

    if not callable(check):
        _errors.append(f"Status service {key!r} needs a callable check.")
        return

    existing = _services.get(key)

    if existing is not None:
        if existing != service:
            _errors.append(
                f"Status service {key!r} is registered twice with different "
                f"definitions."
            )
        return

    _services[key] = service


def register_task_adapter(adapter) -> None:
    """
    Show the tasks of a task backend on the status page: a TaskAdapter
    (content_studio.dashboard.tasks), such as HueyAdapter. Without a
    registered adapter the page uses Huey when it is installed.
    """
    if not any(adapter is known for known in _adapters):
        _adapters.append(adapter)


def register_recurring_task(
    key: str,
    label: StrOrPromise,
    schedule: StrOrPromise = "",
    get_last_run: Optional[Callable[[], Union[datetime, Run, None]]] = None,
    get_next_run: Optional[Callable[[], Optional[datetime]]] = None,
    group: Optional[StrOrPromise] = None,
) -> None:
    """
    Add a recurring task to the status page, or describe one a task
    adapter reports. key is lowercase dotted words; when it is the dotted
    path of a periodic task an adapter reports ("shop.tasks.sync_orders"),
    the two show as one row with this label and schedule.

    schedule says when the task runs, in words: "Every 15 minutes".
    get_last_run returns when the task last ran (a datetime, or a
    status.Run to say that it failed); get_next_run when it runs next.
    group names where the task belongs; by default the app of its key.
    """
    task = RecurringTask(
        key=key,
        label=label,
        schedule=schedule,
        get_last_run=get_last_run,
        get_next_run=get_next_run,
        group=group,
    )

    if not _valid_key("Recurring task", key):
        return

    existing = _recurring.get(key)

    if existing is not None:
        if existing != task:
            _errors.append(
                f"Recurring task {key!r} is registered twice with different "
                f"definitions."
            )
        return

    _recurring[key] = task


def register_task(path: str, label: StrOrPromise) -> None:
    """
    Name a task on the status page: path is the task's dotted path
    ("shop.tasks.sync_orders"). Unnamed tasks show their function name
    in words ("Sync orders").
    """
    _task_labels[path] = label


def get_services() -> list[Service]:
    return list(_services.values())


def get_recurring_tasks() -> list[RecurringTask]:
    return list(_recurring.values())


def get_registered_adapters() -> list[Any]:
    return list(_adapters)


def get_task_label(path: Optional[str]):
    return _task_labels.get(path) if path else None


def registration_errors() -> list[str]:
    return list(_errors)
