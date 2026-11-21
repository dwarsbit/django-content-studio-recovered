"""
The views of the list page beyond the table and the list: a calendar of
the objects by a date field, a board of them in columns by a choice
field or a foreign key, and a gallery of their images.

A studio names its views in list_views, with strings for the views that
need nothing more and objects for those that take a field:

    from content_studio.list_views import BoardView, CalendarView

    class ArticleStudio(ModelStudio):
        list_views = [
            "table",
            "list",
            CalendarView("published_at"),
            BoardView("stage"),
            "gallery",
        ]

"calendar" on its own is the calendar of the studio's publishing date,
so scheduled content needs one word. Dragging an item to another day
saves its new date right away: through the publishing endpoint (it
reschedules) for the publishing date, else through the same save as a
table cell (change permission, hooks, validation, history). Dragging a
board card to another column saves its new value the same way.
"""

from typing import Any, Optional, Union

from django.db import models
from django.db.models import Count, Q
from django.http import HttpRequest
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import capfirst

from ._types import StrOrPromise

__all__ = ["BoardView", "CalendarView"]

# The views named by a plain string in list_views.
VIEW_NAMES = {"table", "list", "calendar", "gallery"}

# The viewset actions that answer with list rows.
ROW_ACTIONS = ("list", "trash", "calendar", "board")

# The most items one calendar request returns; a busier range is cut
# and says so.
CALENDAR_MAX_ITEMS = 500

# The most items the calendar's "no date" tray lists.
CALENDAR_MAX_UNSCHEDULED = 100

# The cards a board column shows at first, and the most it shows after
# "Show more".
BOARD_PAGE_SIZE = 20
BOARD_MAX_PER_COLUMN = 200

# The columns a board of a foreign key shows by default: the first
# related objects.
BOARD_MAX_RELATED_COLUMNS = 12

# The value of the column of items without a value, in requests.
BOARD_NONE = "__none__"


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


class BoardView:
    """
    The list's objects as cards in columns, one per value of a choice
    field or a foreign key.

    field: a model field with choices, or a ForeignKey.
    columns: the values to show as columns, in order; by default every
    choice, or the first related objects of a foreign key (at most
    BOARD_MAX_RELATED_COLUMNS). Items without a value get a leading
    column when the field allows none.
    label: the view's name in the view switch; the field's verbose name
    by default.
    editable: whether editors may drag cards to another column, which
    saves the new value at once (with Undo). On by default; editors
    still need change permission and the field on the edit page.
    """

    type = "board"

    def __init__(
        self,
        field: str,
        *,
        columns: Optional[list[Any]] = None,
        label: Optional[StrOrPromise] = None,
        editable: bool = True,
    ):
        self.field = field
        self.columns = columns
        self.label = label
        self.editable = editable

    def __repr__(self):
        return f"BoardView({self.field!r})"

    def resolve_field(self, studio) -> Optional[str]:
        return self.field

    def key(self, studio) -> str:
        return f"board:{self.field or ''}"


ListView = Union[str, CalendarView, BoardView]


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
    """The kinds of views a studio offers: "table", "list", "calendar",
    "board", "gallery"."""
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


def get_boards(studio) -> list[BoardView]:
    return [view for view in get_views(studio) if isinstance(view, BoardView)]


def find_board(studio, key: Optional[str]) -> Optional[BoardView]:
    """The board with the given key; the first one when no key is
    given."""
    boards = get_boards(studio)

    if not key:
        return boards[0] if boards else None

    return next((view for view in boards if view.key(studio) == key), None)


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


def _board_field(model, name: Optional[str]) -> Optional[models.Field]:
    if not name:
        return None

    try:
        field = model._meta.get_field(name)
    except Exception:
        return None

    if isinstance(field, models.ForeignKey) or (
        getattr(field, "choices", None) and field.concrete and not field.many_to_many
    ):
        return field

    return None


def board_field_error(studio, name: Optional[str]) -> Optional[str]:
    """Why a field cannot drive a board, or None."""
    if not name:
        return "is not set"

    try:
        studio.model._meta.get_field(name)
    except Exception:
        return f"'{name}' is not a field of {studio.model._meta.label}"

    if _board_field(studio.model, name) is None:
        return f"'{name}' is neither a field with choices nor a ForeignKey"

    return None


def board_columns_error(studio, view: BoardView) -> Optional[str]:
    """Why a board's columns cannot be shown, or None: columns that are
    not a list, or values that are not among a choice field's choices.
    (A foreign key's values are objects, checked when the board loads.)"""
    if view.columns is None:
        return None

    if not isinstance(view.columns, (list, tuple)) or not view.columns:
        return "columns must be a non-empty list of values"

    field = _board_field(studio.model, view.field)

    if field is None or isinstance(field, models.ForeignKey):
        return None

    known = {str(value) for value, _label in field.flatchoices}
    unknown = [repr(value) for value in view.columns if str(value) not in known]

    if unknown:
        return f"columns {', '.join(unknown)} are not choices of '{view.field}'"

    return None


def _empty_values(field) -> list[Any]:
    """The values that put an item in the board's "none" column."""
    values: list[Any] = [None]

    if not isinstance(field, models.ForeignKey) and isinstance(
        field, (models.CharField, models.TextField)
    ):
        values.append("")

    return values


def _has_none_column(field) -> bool:
    if isinstance(field, models.ForeignKey):
        return field.null

    return field.null or (
        field.blank and isinstance(field, (models.CharField, models.TextField))
    )


def board_columns(studio, request: HttpRequest, view: BoardView) -> list[dict]:
    """
    A board's columns as {"value", "label"}: the choices of a choice
    field (empty choices left out), the related objects of a foreign
    key the editor may pick (scoped like its picker); view.columns
    picks and orders them. Items without a value go in a leading column
    of value None when the field allows none.
    """
    field = _board_field(studio.model, view.field)

    if field is None:
        return []

    columns = []

    if _has_none_column(field):
        columns.append({"value": None, "label": ""})

    if isinstance(field, models.ForeignKey):
        from .admin import get_relation_display_for
        from .serializers import studio_queryset
        from .utils import get_tenant_scoped_queryset

        related = field.remote_field.model
        queryset = related._default_manager.complex_filter(field.get_limit_choices_to())
        queryset = get_tenant_scoped_queryset(
            request, related, studio_queryset(request, related, queryset)
        )

        if view.columns is not None:
            wanted = [str(value) for value in view.columns]
            found = {
                str(obj.pk): obj
                for obj in queryset.filter(pk__in=list(view.columns or []))
            }
            objects = [found[pk] for pk in wanted if pk in found]
        else:
            objects = list(queryset[:BOARD_MAX_RELATED_COLUMNS])

        for obj in objects:
            columns.append(
                {
                    "value": obj.pk,
                    "label": str(get_relation_display_for(related, obj, request).title),
                }
            )

        return columns

    choices = [
        (value, label)
        for value, label in field.flatchoices
        if value not in _empty_values(field)
    ]

    if view.columns is not None:
        by_value = {str(value): (value, label) for value, label in choices}
        choices = [
            by_value[str(value)] for value in view.columns if str(value) in by_value
        ]

    columns.extend({"value": value, "label": str(label)} for value, label in choices)

    return columns


def _column_filter(field, value) -> Q:
    if value is None:
        query = Q()

        for empty in _empty_values(field):
            query |= (
                Q(**{f"{field.name}__isnull": True})
                if empty is None
                else Q(**{field.name: empty})
            )

        return query

    return Q(**{field.attname: value})


def _column_value(field, raw: str):
    """A column value from a request, as the field stores it; raises
    ValueError for one that does not parse."""
    from django.core.exceptions import ValidationError

    if raw == BOARD_NONE:
        return None

    target = field.target_field if isinstance(field, models.ForeignKey) else field

    try:
        return target.to_python(raw)
    except (ValidationError, TypeError) as error:
        raise ValueError(f"{raw!r} is not a value of '{field.name}'.") from error


def board_data(queryset, studio, request: HttpRequest, view: BoardView, limits=None):
    """
    The board's columns with their counts and first cards:
    [{"value", "label", "count", "rows"}]. limits maps a column value
    (as a request sends it) to how many cards to show, for "Show more".
    """
    field = _board_field(studio.model, view.field)
    columns = board_columns(studio, request, view)
    counts: dict[Any, int] = {}

    grouped = (
        queryset.order_by()
        .values(field.attname)
        .annotate(count=Count("pk", distinct=True))
    )

    for row in grouped:
        value = row[field.attname]
        key = None if value in _empty_values(field) else str(value)
        counts[key] = counts.get(key, 0) + row["count"]

    limits = limits or {}
    data = []

    for column in columns:
        value = column["value"]
        key = None if value is None else str(value)
        limit = limits.get(BOARD_NONE if value is None else str(value))
        limit = min(max(limit or BOARD_PAGE_SIZE, 1), BOARD_MAX_PER_COLUMN)
        rows = list(queryset.filter(_column_filter(field, value))[:limit])
        data.append({**column, "count": counts.get(key, 0), "rows": rows})

    return data


def parse_board_limits(values: list[str]) -> dict[str, int]:
    """The "Show more" limits a request sends as show=<value>:<count>."""
    limits = {}

    for entry in values:
        value, _, count = entry.rpartition(":")

        if not value:
            continue

        try:
            limits[value] = int(count)
        except ValueError:
            continue

    return limits


def get_drag_fields(studio, request: HttpRequest) -> list[str]:
    """
    The fields the editor may save by dragging in a view, through the
    table edit save: the date (and end) of each editable calendar that
    is not the publishing date, and the field of each editable board,
    when the editor may change objects and the edit page writes the
    field.
    """
    from .admin import get_form_field_names, get_readonly_field_names
    from .publishing import get_publishing

    calendars = [view for view in get_calendars(studio) if view.editable]
    boards = [view for view in get_boards(studio) if view.editable]

    if not (calendars or boards) or not studio.has_change_permission(request):
        return []

    config = get_publishing(studio)
    publishing_fields = set(config.field_names) if config is not None else set()
    form_names = get_form_field_names(studio, request)
    readonly = get_readonly_field_names(studio, request)
    candidates = []

    for view in calendars:
        if view.uses_publishing(studio):
            continue

        for name in (view.resolve_field(studio), view.end):
            if name and _date_field(studio.model, name) is not None:
                candidates.append(name)

    for view in boards:
        if _board_field(studio.model, view.field) is not None:
            candidates.append(view.field)

    names = []

    for name in candidates:
        if (
            name not in names
            and name in form_names
            and name not in readonly
            and name not in publishing_fields
        ):
            names.append(name)

    return names


def can_drag(
    studio, request: HttpRequest, view: Union[CalendarView, BoardView]
) -> bool:
    """Whether the editor may drag the view's items at all (rows still
    say whether each one may change)."""
    if not view.editable:
        return False

    if isinstance(view, BoardView):
        return view.field in get_drag_fields(studio, request)

    if view.uses_publishing(studio):
        from .review import get_review, review_enabled

        # With required review, scheduling goes through a review request.
        if review_enabled(studio) and get_review(studio).required:
            return False

        return bool(studio.has_publish_permission(request))

    field = view.resolve_field(studio)
    names = get_drag_fields(studio, request)

    return field in names and (not view.end or view.end in names)


def serialize_view(studio, request: HttpRequest, view: ListView) -> Any:
    """A view as the list page reads it: a name, or an object for the
    views that take a field."""
    if isinstance(view, str):
        return view

    if isinstance(view, BoardView):
        return serialize_board(studio, request, view)

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


def serialize_board(studio, request: HttpRequest, view: BoardView) -> dict:
    field = _board_field(studio.model, view.field)
    label = view.label or (capfirst(field.verbose_name) if field else "")

    return {
        "type": view.type,
        "key": view.key(studio),
        "field": view.field,
        "label": str(label),
        # A foreign key: rows hold {"id", ...}, saves send {"id": value}.
        "relation": isinstance(field, models.ForeignKey),
        # What a card dropped on the column of items without a value
        # saves: "" for text that may be blank but not null.
        "empty_value": (
            ""
            if field is not None
            and not field.null
            and isinstance(field, (models.CharField, models.TextField))
            else None
        ),
        "columns": board_columns(studio, request, view) if field else [],
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
