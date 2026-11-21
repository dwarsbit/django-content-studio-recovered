"""
The views of the list page beyond the table and the list: a calendar of
the objects by a date field.

A studio names its views in list_views, with strings for the views that
need nothing more and objects for those that take a field:

    from content_studio.list_views import CalendarView

    class ArticleStudio(ModelStudio):
        list_views = ["table", "list", CalendarView("published_at")]

"calendar" on its own is the calendar of the studio's publishing date,
so scheduled content needs one word. Dragging an item to another day
saves its new date right away: through the publishing endpoint (it
reschedules) for the publishing date, else through the same save as a
table cell (change permission, hooks, validation, history).
"""

from typing import Any, Optional, Union

from django.db import models
from django.db.models import Q
from django.http import HttpRequest
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import capfirst

from ._types import StrOrPromise

__all__ = ["CalendarView"]

# The views named by a plain string in list_views.
VIEW_NAMES = {"table", "list", "calendar"}

# The viewset actions that answer with list rows.
ROW_ACTIONS = ("list", "trash", "calendar")

# The most items one calendar request returns; a busier range is cut
# and says so.
CALENDAR_MAX_ITEMS = 500

# The most items the calendar's "no date" tray lists.
CALENDAR_MAX_UNSCHEDULED = 100


class CalendarView:
    """
    The list's objects on a month grid, by a date or date-time field.

    field: the model's DateField or DateTimeField; None means the
    studio's publishing date (the same as "calendar" in list_views).
    end: an optional end date field: an object then shows on every day
    from its date through its end.
    label: the view's name in the view switch; the field's verbose name
    by default.
    editable: whether editors may drag items to another day, which
    saves the new date at once (with Undo). On by default; editors still
    need change permission (Can publish for the publishing date).
    """

    type = "calendar"

    def __init__(
        self,
        field: Optional[str] = None,
        *,
        end: Optional[str] = None,
        label: Optional[StrOrPromise] = None,
        editable: bool = True,
    ):
        self.field = field
        self.end = end
        self.label = label
        self.editable = editable

    def __repr__(self):
        return f"CalendarView({self.field!r})"

    def resolve_field(self, studio) -> Optional[str]:
        """The date field: the one named, else the publishing date."""
        if self.field:
            return self.field

        from .publishing import get_publishing

        config = get_publishing(studio)

        return config.published_at if config is not None else None

    def uses_publishing(self, studio) -> bool:
        """Whether this is the calendar of the publishing date, whose
        drags schedule through the publishing endpoint."""
        from .publishing import get_publishing

        config = get_publishing(studio)

        return config is not None and self.resolve_field(studio) == (
            config.published_at
        )

    def key(self, studio) -> str:
        return f"calendar:{self.resolve_field(studio) or ''}"


ListView = Union[str, CalendarView]


def get_views(studio) -> list[ListView]:
    """The studio's list_views, with "calendar" as a CalendarView."""
    views = []

    for view in getattr(studio, "list_views", None) or ["table"]:
        if view == "calendar":
            views.append(CalendarView())
        else:
            views.append(view)

    return views


def view_types(studio) -> set[str]:
    """The kinds of views a studio offers: "table", "list", "calendar"."""
    return {view if isinstance(view, str) else view.type for view in get_views(studio)}


def uses_item_display(studio) -> bool:
    """Whether list rows carry their resolved list_item_display: every
    view but the table draws its items from it."""
    return bool(view_types(studio) - {"table"})


def get_calendars(studio) -> list[CalendarView]:
    return [view for view in get_views(studio) if isinstance(view, CalendarView)]


def find_calendar(studio, key: Optional[str]) -> Optional[CalendarView]:
    """The calendar with the given key; the first one when no key is
    given."""
    calendars = get_calendars(studio)

    if not key:
        return calendars[0] if calendars else None

    return next((view for view in calendars if view.key(studio) == key), None)


def _date_field(model, name: Optional[str]) -> Optional[models.DateField]:
    if not name:
        return None

    try:
        field = model._meta.get_field(name)
    except Exception:
        return None

    # A DateTimeField is a DateField too.
    return field if isinstance(field, models.DateField) else None


def calendar_field_error(studio, name: Optional[str]) -> Optional[str]:
    """Why a field cannot drive a calendar, or None."""
    if not name:
        return "is not set"

    try:
        field = studio.model._meta.get_field(name)
    except Exception:
        return f"'{name}' is not a field of {studio.model._meta.label}"

    if not isinstance(field, models.DateField):
        return f"'{name}' is not a DateField or DateTimeField"

    return None


def get_drag_fields(studio, request: HttpRequest) -> list[str]:
    """
    The fields the editor may save by dragging in a view, through the
    table edit save: the date (and end) of each editable calendar that
    is not the publishing date, when the editor may change objects and
    the edit page writes the field.
    """
    from .admin import get_form_field_names, get_readonly_field_names
    from .publishing import get_publishing

    calendars = [view for view in get_calendars(studio) if view.editable]

    if not calendars or not studio.has_change_permission(request):
        return []

    config = get_publishing(studio)
    publishing_fields = set(config.field_names) if config is not None else set()
    form_names = get_form_field_names(studio, request)
    readonly = get_readonly_field_names(studio, request)
    names = []

    for view in calendars:
        if view.uses_publishing(studio):
            continue

        for name in (view.resolve_field(studio), view.end):
            if (
                name
                and name not in names
                and name in form_names
                and name not in readonly
                and name not in publishing_fields
                and _date_field(studio.model, name) is not None
            ):
                names.append(name)

    return names


def can_drag(studio, request: HttpRequest, view: CalendarView) -> bool:
    """Whether the editor may drag the calendar's items at all (rows
    still say whether each one may change)."""
    if not view.editable:
        return False

    if view.uses_publishing(studio):
        return bool(studio.has_publish_permission(request))

    field = view.resolve_field(studio)
    names = get_drag_fields(studio, request)

    return field in names and (not view.end or view.end in names)


def serialize_view(studio, request: HttpRequest, view: ListView) -> Any:
    """A view as the list page reads it: a name, or an object for the
    views that take a field."""
    if isinstance(view, str):
        return view

    field_name = view.resolve_field(studio)
    field = _date_field(studio.model, field_name)
    label = view.label or (capfirst(field.verbose_name) if field else "")

    return {
        "type": view.type,
        "key": view.key(studio),
        "field": field_name,
        "end": view.end,
        "label": str(label),
        # A DateField is a day without a time.
        "date_only": field is not None and not isinstance(field, models.DateTimeField),
        # Items without a date can be listed (and dropped back) when
        # the field allows none.
        "nullable": bool(field is not None and field.null),
        "publishing": view.uses_publishing(studio),
        "editable": can_drag(studio, request, view),
    }


def serialize_views(studio, request: HttpRequest) -> list[Any]:
    return [serialize_view(studio, request, view) for view in get_views(studio)]


def _parse_bound(value: Optional[str], date_only: bool):
    if not value:
        return None

    if date_only:
        return parse_date(value[:10])

    parsed = parse_datetime(value)

    if parsed is None:
        day = parse_date(value)

        if day is not None:
            from datetime import datetime, time

            from django.utils import timezone

            parsed = timezone.make_aware(datetime.combine(day, time.min))

    return parsed


def filter_range(queryset, studio, view: CalendarView, start: str, stop: str):
    """
    The objects of a calendar range [start, stop): those dated in it
    and, with an end field, those that started before and end in or
    after it. Raises ValueError for bounds that do not parse.
    """
    field_name = view.resolve_field(studio)
    field = _date_field(studio.model, field_name)
    date_only = not isinstance(field, models.DateTimeField)
    low = _parse_bound(start, date_only)
    high = _parse_bound(stop, date_only)

    if low is None or high is None:
        raise ValueError("from and to must be dates.")

    starts_before_end = Q(**{f"{field_name}__lt": high})

    if view.end:
        overlaps = Q(**{f"{view.end}__gte": low}) | Q(
            **{f"{view.end}__isnull": True, f"{field_name}__gte": low}
        )
    else:
        overlaps = Q(**{f"{field_name}__gte": low})

    return queryset.filter(starts_before_end & overlaps)


def filter_unscheduled(queryset, studio, view: CalendarView):
    """The objects without a date, for the calendar's tray."""
    return queryset.filter(**{f"{view.resolve_field(studio)}__isnull": True})
