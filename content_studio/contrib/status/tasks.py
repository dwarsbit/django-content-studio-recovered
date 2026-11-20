"""
The tasks on the status page: what the task adapters report, named and
grouped for reading, with the recurring tasks apps registered.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from django.apps import apps
from django.utils import timezone

from ...dashboard.tasks import TaskRow, TaskStatus
from .registry import (
    Run,
    get_recurring_tasks,
    get_registered_adapters,
    get_task_label,
)
from .runner import app_name

logger = logging.getLogger(__name__)

HUEY_APP = "huey.contrib.djhuey"

# Rows per list.
LIMIT = 20
# How long past its time a recurring task may be before it shows as due.
OVERDUE_AFTER = timedelta(minutes=1)
# The window the failure count covers without adapter statistics.
FAILED_WINDOW = timedelta(hours=24)

_huey_adapter = None


def get_adapters() -> list[Any]:
    """
    The registered task adapters; without any, a HueyAdapter for
    djhuey's queue when Huey is installed.
    """
    global _huey_adapter

    adapters = get_registered_adapters()

    if adapters:
        return adapters

    if apps.is_installed(HUEY_APP):
        if _huey_adapter is None:
            from ..huey import HueyAdapter

            _huey_adapter = HueyAdapter()
        return [_huey_adapter]

    return []


def humanize(name: str) -> str:
    """sync_orders and SyncOrders read "Sync orders"."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").split()
    text = " ".join(words).lower()
    return text[:1].upper() + text[1:]


def get_title(row: TaskRow) -> str:
    label = get_task_label(row.key)

    if label:
        return str(label)
    if row.key:
        return humanize(row.key.rpartition(".")[2])
    return str(row.title)


def get_source(row: TaskRow) -> str:
    if row.source:
        return str(row.source)

    name = app_name(row.key.rpartition(".")[0]) if row.key else None
    return str(name) if name else str(row.description or "")


def iso(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else value.isoformat()


def serialize_run(row: TaskRow) -> dict:
    return {
        "key": row.key,
        "title": get_title(row),
        "source": get_source(row),
        "status": str(row.status),
        "at": iso(row.last_run_at),
        "duration": row.duration,
        "error_message": row.error_message or None,
    }


def is_overdue(next_run_at: Optional[datetime], running: bool, now: datetime) -> bool:
    return bool(next_run_at and not running and next_run_at < now - OVERDUE_AFTER)


def serialize_periodic(row: TaskRow, now: datetime) -> dict:
    # A task that never ran is SCHEDULED: it has no last status.
    last = None if row.status == TaskStatus.SCHEDULED else str(row.status)

    return {
        "key": row.key,
        "title": get_title(row),
        "source": get_source(row),
        "schedule": str(row.schedule or ""),
        "next_run_at": iso(row.next_run_at),
        "last_run_at": iso(row.last_run_at),
        "last_status": last,
        "error_message": row.error_message or None,
        "overdue": is_overdue(row.next_run_at, row.status == TaskStatus.RUNNING, now),
    }


def apply_registered(rows: list[dict], now: datetime) -> list[dict]:
    """
    Merge the registered recurring tasks into the adapters' rows: one
    with the key of a row describes it, the others are rows of their own.
    """
    by_key = {row["key"]: row for row in rows if row["key"]}

    for task in get_recurring_tasks():
        row = by_key.get(task.key)

        if row is None:
            group = task.group or app_name(task.key.rpartition(".")[0])
            row = {
                "key": task.key,
                "title": "",
                "source": str(group) if group else "",
                "schedule": "",
                "next_run_at": None,
                "last_run_at": None,
                "last_status": None,
                "error_message": None,
                "overdue": False,
            }
            rows.append(row)
        elif task.group:
            row["source"] = str(task.group)

        row["title"] = str(task.label)

        if task.schedule:
            row["schedule"] = str(task.schedule)

        try:
            if task.get_last_run is not None:
                last = task.get_last_run()

                if isinstance(last, Run):
                    row["last_run_at"] = iso(last.at)
                    row["last_status"] = (
                        str(TaskStatus.SUCCESS if last.ok else TaskStatus.FAILURE)
                        if last.at
                        else None
                    )
                    row["error_message"] = str(last.message) if last.message else None
                elif last is not None:
                    row["last_run_at"] = iso(last)
                    row["last_status"] = str(TaskStatus.SUCCESS)

            if task.get_next_run is not None:
                next_run_at = task.get_next_run()
                row["next_run_at"] = iso(next_run_at)
                row["overdue"] = is_overdue(
                    next_run_at, row["last_status"] == TaskStatus.RUNNING, now
                )
        except Exception as exc:
            logger.warning(
                "Recurring task %s failed to report.", task.key, exc_info=True
            )
            row["error_message"] = f"{type(exc).__name__}: {exc}"

    return rows


def get_tasks(request) -> dict:
    adapters = get_adapters()
    now = timezone.now()
    pending: list[TaskRow] = []
    finished: list[TaskRow] = []
    periodic: list[TaskRow] = []
    errors: list[str] = []
    counted_pending = counted_failed = None

    for adapter in adapters:
        try:
            if adapter.implements("get_pending_tasks"):
                pending += adapter.get_pending_tasks(request, LIMIT)
            if adapter.implements("get_recent_tasks"):
                finished += adapter.get_recent_tasks(request, LIMIT)
            if adapter.implements("get_periodic_tasks"):
                periodic += adapter.get_periodic_tasks(request)
            if adapter.implements("get_statistics"):
                statistics = adapter.get_statistics(request)

                if "queued" in statistics:
                    counted_pending = (counted_pending or 0) + sum(
                        statistics[name].value
                        for name in ("queued", "running")
                        if name in statistics
                    )
                if "failed" in statistics:
                    counted_failed = (counted_failed or 0) + statistics["failed"].value
        except Exception as exc:
            logger.warning(
                "Task adapter %s failed.", type(adapter).__name__, exc_info=True
            )
            errors.append(f"{type(adapter).__name__}: {type(exc).__name__}: {exc}")

    # Running before queued, then the latest finished first.
    pending.sort(key=lambda row: row.status != TaskStatus.RUNNING)
    finished = [row for row in finished if row.last_run_at is not None]
    finished.sort(key=lambda row: row.last_run_at, reverse=True)
    pending, finished = pending[:LIMIT], finished[:LIMIT]

    if counted_pending is None:
        counted_pending = len(pending)
    if counted_failed is None:
        counted_failed = sum(
            1
            for row in finished
            if row.status == TaskStatus.FAILURE
            and row.last_run_at >= now - FAILED_WINDOW
        )

    recurring = apply_registered(
        [serialize_periodic(row, now) for row in periodic], now
    )
    recurring.sort(key=lambda row: row["title"].lower())

    return {
        # Whether a task backend reports its tasks; the recurring tasks
        # apps registered show either way.
        "connected": bool(adapters),
        "pending": [serialize_run(row) for row in pending],
        "finished": [serialize_run(row) for row in finished],
        "recurring": recurring,
        "counts": {"pending": counted_pending, "failed": counted_failed},
        "errors": errors,
    }
