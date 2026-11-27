"""
Daily counts of the challenges the widget solved and failed, kept for the
dashboard's CaptchaStatisticWidget: the challenges themselves are deleted
when they are redeemed.
"""

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

# Days of counts kept; older rows go with the cleanup of each new challenge.
KEEP_DAYS = 366

METRICS = ("solved", "failed")


def count(metric: str, day: date | None = None) -> None:
    """Adds one to today's ``metric``: "solved" or "failed"."""
    from .models import DailyCount

    if metric not in METRICS:
        raise ValueError(f"Unknown captcha metric {metric!r}.")
    day = day or timezone.localdate()
    increment = {metric: F(metric) + 1}

    if DailyCount.objects.filter(date=day).update(**increment):
        return
    try:
        with transaction.atomic():
            DailyCount.objects.create(date=day, **{metric: 1})
    except IntegrityError:
        # Another request created today's row first.
        DailyCount.objects.filter(date=day).update(**increment)


def prune() -> None:
    from .models import DailyCount

    DailyCount.objects.filter(
        date__lt=timezone.localdate() - timedelta(days=KEEP_DAYS)
    ).delete()


def daily(metric: str, start: date, end: date) -> list[int]:
    """``metric`` for each day from ``start`` to ``end``, both included, 0 for days without a row."""
    from .models import DailyCount

    values = dict(
        DailyCount.objects.filter(date__gte=start, date__lte=end).values_list(
            "date", metric
        )
    )
    days = (end - start).days + 1
    return [values.get(start + timedelta(days=offset), 0) for offset in range(days)]
