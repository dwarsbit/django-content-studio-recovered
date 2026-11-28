"""
The audit log's timeline: activity log entries (LogEntry) and sign-in
events merged into one list, newest first, filtered and paged by a
cursor.

Both sources are ordered by the key (time, rank, pk), sign-in events
ranking below changes at the same instant, so a cursor (the key of the
last item shown) picks up exactly where a page ended in both.
"""

import datetime
import ipaddress
from dataclasses import dataclass, field
from typing import Any, Optional

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from ...dashboard.activity_log import (
    tenant_scoped_models,
    viewable_content_type_ids,
    visible_entries,
)
from .models import SignInEvent

CHANGES = "change"
SIGN_INS = "sign_in"

# Rank of each source among items at the same time.
RANKS = {SIGN_INS: 0, CHANGES: 1}

CHANGE_ACTIONS = [
    "created",
    "updated",
    "deleted",
    "restored",
    "reordered",
    "published",
    "unpublished",
]
SIGN_IN_ACTIONS = [
    SignInEvent.SIGNED_IN,
    SignInEvent.FAILED,
    SignInEvent.SIGNED_OUT,
]
ACTIONS = [*CHANGE_ACTIONS, *SIGN_IN_ACTIONS]

FLAG_ACTIONS = {ADDITION: "created", CHANGE: "updated", DELETION: "deleted"}

# Actions that only EntryAction tells apart from a change.
RECORDED_ACTIONS = {"restored", "reordered", "published", "unpublished"}

# The longest search taken.
MAX_QUERY = 200

# Change entries read at most per page when entries of other tenants are
# skipped; a page may then come back short, with a cursor to go on.
MAX_SCANNED = 1000


@dataclass
class Filters:
    user: Optional[str] = None
    model: Optional[ContentType] = None
    object_id: Optional[str] = None
    action: Optional[str] = None
    since: Optional[datetime.datetime] = None
    until: Optional[datetime.datetime] = None
    query: str = ""
    # A filter no entry can match, such as a malformed user id.
    nothing: bool = False


@dataclass(frozen=True, order=True)
class Key:
    time: datetime.datetime
    rank: int
    pk: int

    def encode(self) -> str:
        return f"{self.time.isoformat()}~{self.rank}~{self.pk}"

    @classmethod
    def decode(cls, value: str) -> Optional["Key"]:
        try:
            time, rank, pk = value.split("~")
            time = datetime.datetime.fromisoformat(time)
        except (AttributeError, ValueError):
            return None

        if timezone.is_naive(time):
            time = timezone.make_aware(time, datetime.timezone.utc)

        try:
            return cls(time, int(rank), int(pk))
        except ValueError:
            return None


@dataclass
class Item:
    source: str
    obj: Any
    key: Key = field(init=False)

    def __post_init__(self):
        time = self.obj.action_time if self.source == CHANGES else self.obj.created_at
        self.key = Key(time, RANKS[self.source], self.obj.pk)


def parse_bound(value, end: bool = False) -> Optional[datetime.datetime]:
    """
    A date or date-time from the query string, aware. A date stands for
    its start, or with end for the start of the next day.
    """
    if not value:
        return None

    try:
        # A date alone; parse_datetime() would read it as midnight.
        day = parse_date(value)
    except ValueError:
        return None

    if day is not None:
        if end:
            day += datetime.timedelta(days=1)

        moment = datetime.datetime.combine(day, datetime.time.min)
    else:
        try:
            moment = parse_datetime(value)
        except ValueError:
            return None

        if moment is None:
            return None

    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)

    return moment


def parse_filters(params) -> Filters:
    filters = Filters()

    user = params.get("user")

    if user:
        try:
            filters.user = get_user_model()._meta.pk.to_python(user)
        except DjangoValidationError:
            filters.nothing = True

    model = params.get("model") or ""

    if "." in model:
        app_label, model_name = model.split(".", 1)
        filters.model = ContentType.objects.filter(
            app_label=app_label, model=model_name.lower()
        ).first()

        if filters.model is None:
            filters.nothing = True

    if filters.model is not None:
        filters.object_id = params.get("object") or None

    action = params.get("action")
    filters.action = action if action in ACTIONS else None
    filters.since = parse_bound(params.get("since"))
    filters.until = parse_bound(params.get("until"), end=True)
    filters.query = (params.get("q") or "").strip()[:MAX_QUERY]

    return filters


def _before(key: Optional[Key], source: str, time_field: str) -> Q:
    """The rows of a source that come after key in the timeline."""
    if key is None:
        return Q()

    rank = RANKS[source]
    earlier = Q(**{f"{time_field}__lt": key.time})

    if rank < key.rank:
        return earlier | Q(**{time_field: key.time})
    if rank == key.rank:
        return earlier | Q(**{time_field: key.time, "pk__lt": key.pk})

    return earlier


def change_queryset(request, filters: Filters, key: Optional[Key]):
    """
    The activity log entries the filters keep and the content types they
    are of, or None for none.
    """
    if filters.nothing or filters.action in SIGN_IN_ACTIONS:
        return None

    content_types = viewable_content_type_ids(request)

    if filters.model is not None:
        if filters.model.pk not in content_types:
            return None

        content_types = [filters.model.pk]

    entries = LogEntry.objects.filter(content_type_id__in=content_types)

    if filters.object_id is not None:
        entries = entries.filter(object_id=filters.object_id)

    if filters.user is not None:
        entries = entries.filter(user_id=filters.user)

    action = filters.action

    if action == "created":
        entries = entries.filter(action_flag=ADDITION)
    elif action == "deleted":
        entries = entries.filter(action_flag=DELETION)
    elif action == "updated":
        entries = entries.filter(action_flag=CHANGE).filter(
            Q(content_studio_action__isnull=True)
            | Q(content_studio_action__action="updated")
        )
    elif action in RECORDED_ACTIONS:
        entries = entries.filter(content_studio_action__action=action)

    if filters.since is not None:
        entries = entries.filter(action_time__gte=filters.since)

    if filters.until is not None:
        entries = entries.filter(action_time__lt=filters.until)

    if filters.query:
        entries = entries.filter(
            Q(object_repr__icontains=filters.query)
            | Q(change_message__icontains=filters.query)
        )

    entries = (
        entries.filter(_before(key, CHANGES, "action_time"))
        .select_related("user", "content_type", "content_studio_action")
        .order_by("-action_time", "-pk")
    )

    return entries, content_types


def sign_in_queryset(filters: Filters, key: Optional[Key]):
    """The sign-in events the filters keep, or None for none."""
    if filters.nothing or filters.model is not None or filters.action in CHANGE_ACTIONS:
        return None

    events = SignInEvent.objects.all()

    if filters.user is not None:
        events = events.filter(user_id=filters.user)

    if filters.action is not None:
        events = events.filter(kind=filters.action)

    if filters.since is not None:
        events = events.filter(created_at__gte=filters.since)

    if filters.until is not None:
        events = events.filter(created_at__lt=filters.until)

    if filters.query:
        try:
            address = str(ipaddress.ip_address(filters.query))
        except ValueError:
            address = None

        match = Q(username__icontains=filters.query)

        if address is not None:
            match |= Q(ip_address=address)

        events = events.filter(match)

    return (
        events.filter(_before(key, SIGN_INS, "created_at"))
        .select_related("user")
        .order_by("-created_at", "-pk")
    )


def _read_changes(request, queryset, content_types, limit):
    """
    Up to limit + 1 visible entries: (items, exhausted, boundary), where
    boundary is the key of the last entry read, visible or not.
    """
    scoped = tenant_scoped_models(content_types)

    if not scoped:
        rows = list(queryset[: limit + 1])
        items = [Item(CHANGES, row) for row in rows]
        exhausted = len(rows) <= limit
        return items, exhausted, items[-1].key if items else None

    items = []
    boundary = None
    batch_size = max(limit * 2, 50)

    for offset in range(0, MAX_SCANNED, batch_size):
        batch = list(queryset[offset : offset + batch_size])

        if batch:
            boundary = Item(CHANGES, batch[-1]).key

        items += [Item(CHANGES, row) for row in visible_entries(request, batch, scoped)]

        if len(batch) < batch_size:
            return items, True, boundary

        if len(items) > limit:
            break

    return items, False, boundary


def get_page(request, filters: Filters, cursor: Optional[Key], limit: int):
    """
    One page of the timeline after cursor: (items, next cursor), the
    next cursor None at the end.
    """
    sources = []
    changes = change_queryset(request, filters, cursor)
    sign_ins = sign_in_queryset(filters, cursor)

    if changes is not None:
        sources.append(_read_changes(request, *changes, limit))

    if sign_ins is not None:
        rows = list(sign_ins[: limit + 1])
        items = [Item(SIGN_INS, row) for row in rows]
        sources.append((items, len(rows) <= limit, items[-1].key if items else None))

    # Items past the last row read from a source that has more could be
    # followed by unread rows of it: they wait for the next page.
    open_boundaries = [
        boundary
        for _items, exhausted, boundary in sources
        if not exhausted and boundary is not None
    ]
    threshold = max(open_boundaries) if open_boundaries else None

    merged = sorted(
        (item for items, _exhausted, _boundary in sources for item in items),
        key=lambda item: item.key,
        reverse=True,
    )

    if threshold is not None:
        merged = [item for item in merged if item.key >= threshold]

    page = merged[:limit]
    more = len(merged) > limit or threshold is not None

    if not more:
        return page, None

    if page:
        return page, page[-1].key

    return page, threshold
