"""
BACKUP_SCHEDULE: a cron expression of five fields (minute, hour, day of
the month, month, day of the week), like "0 3 * * *" for daily at 03:00.
The same expression drives Huey's periodic task and the line in your
crontab, and tells the status page when the next backup is due.

Each field is "*", a number, a range ("1-5"), a list ("1,15") or a step
("*/15", "0-30/10"). Days of the week run from 0 (Sunday) to 6; 7 is
Sunday too.
"""

import datetime
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone
from django.utils.translation import gettext as _

# (name, lowest, highest) per field, in order.
FIELDS = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),
]

# How far ahead the next run is looked for.
HORIZON = datetime.timedelta(days=366)

WEEKDAYS = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]


class ScheduleError(ValueError):
    pass


def parse_field(text: str, name: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()

    for part in text.split(","):
        step = 1

        if "/" in part:
            part, _slash, step_text = part.partition("/")
            if not step_text.isdigit() or int(step_text) < 1:
                raise ScheduleError(f"{name}: {step_text!r} is not a step.")
            step = int(step_text)

        if part == "*":
            start, end = low, high
        elif "-" in part:
            start_text, _dash, end_text = part.partition("-")
            if not (start_text.isdigit() and end_text.isdigit()):
                raise ScheduleError(f"{name}: {part!r} is not a range.")
            start, end = int(start_text), int(end_text)
        elif part.isdigit():
            start = end = int(part)
            if step != 1:
                end = high
        else:
            raise ScheduleError(f"{name}: {part!r} is not a number.")

        top = 7 if name == "day_of_week" else high

        if start < low or end > top or start > end:
            raise ScheduleError(f"{name}: {part!r} is outside {low}-{high}.")

        values.update(range(start, end + 1, step))

    if name == "day_of_week" and 7 in values:
        values.discard(7)
        values.add(0)

    return frozenset(values)


@dataclass(frozen=True)
class Schedule:
    expression: str
    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    day_of_week: frozenset[int]
    # Whether the day of the month and the day of the week are both
    # restricted: then either one matching is enough, as in cron.
    either_day: bool

    def matches(self, moment: datetime.datetime) -> bool:
        if moment.minute not in self.minute or moment.hour not in self.hour:
            return False
        if moment.month not in self.month:
            return False

        weekday = (moment.weekday() + 1) % 7
        day = moment.day in self.day
        week = weekday in self.day_of_week

        return (day or week) if self.either_day else (day and week)

    def _days(self, start: datetime.date, step: int):
        day = start
        for _i in range(HORIZON.days + 1):
            yield day
            day += datetime.timedelta(days=step)

    def _day_matches(self, day: datetime.date) -> bool:
        if day.month not in self.month:
            return False
        weekday = (day.weekday() + 1) % 7
        in_day = day.day in self.day
        in_week = weekday in self.day_of_week
        return (in_day or in_week) if self.either_day else (in_day and in_week)

    def next_after(self, moment: datetime.datetime) -> Optional[datetime.datetime]:
        """The first run after moment (aware), in moment's time zone."""
        tz = moment.tzinfo
        start = moment.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        times = sorted((h, m) for h in self.hour for m in self.minute)

        for day in self._days(start.date(), 1):
            if not self._day_matches(day):
                continue
            for hour, minute in times:
                candidate = datetime.datetime(
                    day.year, day.month, day.day, hour, minute, tzinfo=tz
                )
                if candidate >= start:
                    return candidate
        return None

    def describe(self) -> str:
        """The schedule in words: "Daily at 03:00", or the expression."""
        fields = self.expression.split()
        minute, hour, day, month, weekday = fields

        if minute.isdigit() and hour.isdigit() and day == month == "*":
            at = f"{int(hour):02d}:{int(minute):02d}"
            if weekday == "*":
                return _("Daily at %(time)s") % {"time": at}
            if weekday.isdigit():
                return _("Weekly on %(day)s at %(time)s") % {
                    "day": _(WEEKDAYS[int(weekday) % 7]),
                    "time": at,
                }
        if minute.isdigit() and hour == day == month == weekday == "*":
            return _("Hourly at %(minute)s past") % {"minute": f":{int(minute):02d}"}
        if (
            minute.isdigit()
            and hour.startswith("*/")
            and hour[2:].isdigit()
            and day == month == weekday == "*"
        ):
            return _("Every %(hours)s hours") % {"hours": hour[2:]}

        return _("Cron: %(expression)s") % {"expression": self.expression}

    def huey_crontab_kwargs(self) -> dict:
        """The arguments of Huey's crontab() for this schedule."""
        minute, hour, day, month, weekday = self.expression.split()
        return {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": weekday.replace("7", "0"),
        }


def parse(expression: str) -> Schedule:
    """The schedule of a cron expression; ScheduleError when it is not one."""
    if not isinstance(expression, str):
        raise ScheduleError("A schedule is a cron expression, like '0 3 * * *'.")

    parts = expression.split()

    if len(parts) != 5:
        raise ScheduleError(
            "A schedule has five fields: minute, hour, day, month, day of the week."
        )

    values = {
        name: parse_field(part, name, low, high)
        for part, (name, low, high) in zip(parts, FIELDS)
    }

    return Schedule(
        expression=" ".join(parts),
        either_day=parts[2] != "*" and parts[4] != "*",
        **values,
    )


def get_schedule() -> Optional[Schedule]:
    """The BACKUP_SCHEDULE, or None when there is none (or it is invalid)."""
    from ...settings import cs_settings

    expression = cs_settings.BACKUP_SCHEDULE

    if not expression:
        return None

    try:
        return parse(expression)
    except ScheduleError:
        return None


def get_timezone() -> datetime.tzinfo:
    """
    The time zone the schedule is read in: UTC when Huey runs it with
    its default utc=True, otherwise Django's TIME_ZONE (and your server's
    time zone for cron).
    """
    from .huey import get_huey

    huey = get_huey()

    if huey is not None and getattr(huey, "utc", True):
        return datetime.timezone.utc

    return timezone.get_default_timezone()


def next_run(after: Optional[datetime.datetime] = None):
    schedule = get_schedule()

    if schedule is None:
        return None

    after = (after or timezone.now()).astimezone(get_timezone())
    return schedule.next_after(after)
