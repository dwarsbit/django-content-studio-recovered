"""
Draft, publish and scheduling: an opt-in on a ModelStudio.

A studio names its model's publish date field, the way soft_delete
names the trash field:

    class ArticleStudio(ModelStudio):
        publishing = Publishing("published_at", unpublish_at="unpublish_at")

    # or, with only a publish date:
    class PageStudio(ModelStudio):
        publishing = "published_at"

An object's state follows from its dates, so nothing has to run for
content to go live or expire on time:

- draft: no publish date;
- scheduled: a publish date in the future;
- published: a publish date that passed, and no unpublish date or one
  in the future;
- expired: an unpublish date that passed.

The edit page's Publishing card and the list's bulk actions change the
dates through the publishing endpoint; the normal form never writes
them. Changing them needs the model's "Can publish" permission
(publish_<model>), which is created for every publishable model.

What happens at the moment content goes live or comes down (the
activity log, content_changed with the "published" and "unpublished"
actions, a status field kept in step, the studio's on_publish and
on_unpublish hooks) is done by run_scheduled(): a Huey periodic task
every minute when Huey is installed, else content_studio_publish from
cron.
"""

import datetime
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models, router, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ._types import StrOrPromise

__all__ = [
    "DRAFT",
    "EXPIRED",
    "PUBLISHED",
    "SCHEDULED",
    "Publishing",
    "get_state",
    "live",
    "run_scheduled",
]

logger = logging.getLogger("content_studio.publishing")

DRAFT = "draft"
SCHEDULED = "scheduled"
PUBLISHED = "published"
EXPIRED = "expired"

STATES = (DRAFT, SCHEDULED, PUBLISHED, EXPIRED)

STATE_LABELS = {
    DRAFT: _("Draft"),
    SCHEDULED: _("Scheduled"),
    PUBLISHED: _("Published"),
    EXPIRED: _("Expired"),
}

# The activity log's messages. They are stored as written, like
# "Moved.", and the sweep finds the changes it already handled by them.
MESSAGE_PUBLISHED = "Published."
MESSAGE_UNPUBLISHED = "Unpublished."
MESSAGE_UNSCHEDULED = "Unscheduled."
MESSAGE_PUBLISHED_ON_SCHEDULE = "Published on schedule."
MESSAGE_UNPUBLISHED_ON_SCHEDULE = "Unpublished on schedule."
MESSAGE_SCHEDULED_PREFIX = "Scheduled to publish on "
MESSAGE_UNPUBLISH_DATE_PREFIX = "Set the unpublish date to "
MESSAGE_UNPUBLISH_DATE_REMOVED = "Removed the unpublish date."

# How far back the sweep looks for content whose date passed: a worker
# that was down for less catches up, with the log entries and signals.
CATCH_UP = datetime.timedelta(days=1)

# The cache key of the sweep's last run, for the status page.
LAST_RUN_CACHE_KEY = "content_studio:publishing:last_run"

# The Status filter's option for objects with unpublished changes (see
# content_studio.pending).
PENDING = "pending"

# The column and filter names the list uses.
STATUS_COLUMN = "__publishing__"
STATUS_FILTER = "publishing_status"

ACTIONS = ("publish", "schedule", "unpublish", "set_unpublish_at")


class Publishing:
    """
    The publishing configuration of a studio.

    published_at names the model's nullable DateTimeField that holds
    the publish date (required). unpublish_at names an optional
    nullable DateTimeField: content expires once it passes. status
    names an optional field that is kept in step with the state, with
    status_values mapping the states to its values:

        Publishing(
            "published_at",
            status="status",
            status_values={"draft": "draft", "published": "published"},
        )

    A state without a value of its own takes the draft value.

    pending_changes=True keeps edits to published content out of sight
    until they are published: saving a live object stores the changes
    as unpublished changes (see content_studio.pending), and Publish
    changes makes them live. It needs the history app
    (content_studio.history), which stores them.
    """

    def __init__(
        self,
        published_at: str = "published_at",
        *,
        unpublish_at: Optional[str] = None,
        status: Optional[str] = None,
        status_values: Optional[Mapping[str, Any]] = None,
        pending_changes: bool = False,
    ):
        self.published_at = published_at
        self.pending_changes = bool(pending_changes)
        self.unpublish_at = unpublish_at or None
        self.status = status or None
        self.status_values = dict(status_values or {})

    def __repr__(self):
        return f"Publishing({self.published_at!r})"

    @property
    def field_names(self) -> list[str]:
        """The model fields publishing writes: never written by the form."""
        return [
            name for name in (self.published_at, self.unpublish_at, self.status) if name
        ]

    def status_value(self, state: str):
        """The status field's value for a state."""
        if state in self.status_values:
            return self.status_values[state]

        return self.status_values.get(DRAFT)

    def serialize(self) -> dict[str, Any]:
        return {
            "published_at": self.published_at,
            "unpublish_at": self.unpublish_at,
            "pending_changes": self.pending_changes,
        }


def get_publishing(studio) -> Optional[Publishing]:
    """A studio's publishing configuration, or None without one."""
    value = getattr(studio, "publishing", None)

    if isinstance(value, Publishing):
        return value

    if isinstance(value, str) and value:
        return Publishing(value)

    return None


def _now(now=None):
    return now if now is not None else timezone.now()


def state_q(config: Publishing, state: str, now=None) -> Q:
    """The filter of the objects in a state at a time."""
    now = _now(now)
    published_at = config.published_at

    if state == DRAFT:
        return Q(**{f"{published_at}__isnull": True})

    if state == SCHEDULED:
        return Q(**{f"{published_at}__gt": now})

    passed = Q(**{f"{published_at}__lte": now})

    if not config.unpublish_at:
        return passed if state == PUBLISHED else Q(pk__in=[])

    unpublish_at = config.unpublish_at
    expired = Q(**{f"{unpublish_at}__lte": now})

    if state == EXPIRED:
        return passed & expired

    return passed & ~expired


def filter_state(queryset, config: Publishing, states, now=None):
    """The objects of a queryset in any of the given states."""
    query = Q(pk__in=[])

    for state in states:
        query |= state_q(config, state, now)

    return queryset.filter(query)


def get_state(config: Publishing, obj, now=None) -> str:
    """The state of an object at a time (now by default)."""
    now = _now(now)
    published_at = getattr(obj, config.published_at, None)

    if published_at is None:
        return DRAFT

    if published_at > now:
        return SCHEDULED

    unpublish_at = (
        getattr(obj, config.unpublish_at, None) if config.unpublish_at else None
    )

    if unpublish_at is not None and unpublish_at <= now:
        return EXPIRED

    return PUBLISHED


def live(queryset, publishing="published_at", now=None):
    """
    The published objects of a queryset, for the site: their publish
    date passed and their unpublish date, if any, did not.

        live(Article.objects.all(), ArticleStudio.publishing)

    publishing is a Publishing, a field name, or a studio.
    """
    if not isinstance(publishing, (Publishing, str)):
        publishing = get_publishing(publishing)

    if isinstance(publishing, str):
        publishing = Publishing(publishing)

    return queryset.filter(state_q(publishing, PUBLISHED, now))


def get_codename(model) -> str:
    """The codename of a model's publish permission."""
    return f"publish_{model._meta.model_name}"


def get_publishing_studios(site=None) -> list:
    """The registered studios that configure publishing."""
    from .settings import cs_settings

    site = site or cs_settings.ADMIN_SITE

    return [
        studio
        for studio in site._registry.values()
        if get_publishing(studio) is not None
    ]


def create_permissions(sender=None, using="default", apps=None, **kwargs):
    """
    Create the "Can publish" permission of every publishable model, after
    migrate (like Django's own permissions).
    """
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    for studio in get_publishing_studios():
        model = studio.model
        opts = model._meta

        if sender is not None and getattr(sender, "label", None) != opts.app_label:
            continue

        if not router.allow_migrate_model(using, Permission):
            continue

        content_type = ContentType.objects.db_manager(using).get_for_model(
            model, for_concrete_model=False
        )
        Permission.objects.using(using).get_or_create(
            content_type=content_type,
            codename=get_codename(model),
            defaults={"name": f"Can publish {opts.verbose_name_raw}"[:255]},
        )


def serialize_state(config: Publishing, obj, now=None) -> dict[str, Any]:
    """What the list and the edit page show of an object's publishing."""

    def iso(value):
        return value.isoformat() if value is not None else None

    return {
        "state": get_state(config, obj, now),
        "published_at": iso(getattr(obj, config.published_at, None)),
        "unpublish_at": (
            iso(getattr(obj, config.unpublish_at, None))
            if config.unpublish_at
            else None
        ),
    }


def _format_time(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M %Z").strip()


def _parse_time(value, name):
    from django.utils.dateparse import parse_datetime

    if value in (None, ""):
        return None

    parsed = parse_datetime(value) if isinstance(value, str) else value

    if not isinstance(parsed, datetime.datetime):
        raise ValidationError({name: [_("Enter a valid date and time.")]})

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)

    return parsed


@dataclass
class Result:
    """What a publishing change did, for the response and the log."""

    message: str
    action: str
    state: str


def apply(studio, request, obj, action: str, data: Mapping[str, Any]) -> Result:
    """
    Change the publishing of one object, as the edit page's Publishing
    card asks:

    - publish: live now (an expired object's unpublish date is cleared);
    - schedule: live at data["at"], with an optional data["unpublish_at"];
    - unpublish: back to a draft (cancels a schedule);
    - set_unpublish_at: set or clear the unpublish date.

    Records the change, sends content_changed, and calls the studio's
    on_publish or on_unpublish when the object went live or came down.
    Raises ValidationError for a date that does not fit.
    """
    from .signals import UPDATED, record_change

    config = get_publishing(studio)
    now = timezone.now()
    before = get_state(config, obj, now)
    values = {}

    if action == "publish":
        values[config.published_at] = now

        if config.unpublish_at and before == EXPIRED:
            values[config.unpublish_at] = None

        message = MESSAGE_PUBLISHED

    elif action == "schedule":
        at = _parse_time(data.get("at"), "at")

        if at is None:
            raise ValidationError({"at": [_("Pick when to publish.")]})

        if at <= now:
            raise ValidationError({"at": [_("Pick a time in the future.")]})

        values[config.published_at] = at
        message = MESSAGE_SCHEDULED_PREFIX + _format_time(at) + "."

        if config.unpublish_at and "unpublish_at" in data:
            values[config.unpublish_at] = _check_unpublish_at(
                _parse_time(data.get("unpublish_at"), "unpublish_at"), at
            )

    elif action == "unpublish":
        values[config.published_at] = None

        if config.unpublish_at:
            values[config.unpublish_at] = None

        message = MESSAGE_UNSCHEDULED if before == SCHEDULED else MESSAGE_UNPUBLISHED

    elif action == "set_unpublish_at":
        if not config.unpublish_at:
            raise ValidationError(_("This model has no unpublish date."))

        if before == DRAFT:
            raise ValidationError(
                _("Publish or schedule the object before setting an unpublish date.")
            )

        unpublish_at = _check_unpublish_at(
            _parse_time(data.get("unpublish_at"), "unpublish_at"),
            max(getattr(obj, config.published_at), now),
        )
        values[config.unpublish_at] = unpublish_at
        message = (
            MESSAGE_UNPUBLISH_DATE_PREFIX + _format_time(unpublish_at) + "."
            if unpublish_at
            else MESSAGE_UNPUBLISH_DATE_REMOVED
        )

    else:
        raise ValidationError(
            _("Unknown publishing action %(action)s.") % {"action": action}
        )

    for name, value in values.items():
        setattr(obj, name, value)

    after = get_state(config, obj, now)

    if config.status:
        values[config.status] = config.status_value(after)
        setattr(obj, config.status, values[config.status])

    using = router.db_for_write(type(obj))

    with transaction.atomic(using=using):
        type(obj)._base_manager.using(using).filter(pk=obj.pk).update(**values)

        went_live = after == PUBLISHED and before != PUBLISHED
        came_down = before == PUBLISHED and after != PUBLISHED

        if went_live:
            change_action = PUBLISHED
        elif came_down:
            change_action = "unpublished"
        else:
            change_action = UPDATED

        record_change(request, obj, change_action, message)

        if went_live:
            studio.on_publish(request, obj)
        elif came_down:
            studio.on_unpublish(request, obj)

    return Result(message=message, action=change_action, state=after)


def _check_unpublish_at(value, published_at):
    if value is not None and value <= published_at:
        raise ValidationError(
            {"unpublish_at": [_("The unpublish date must be after the publish date.")]}
        )

    return value


def _find_user(content_type, object_id):
    """The editor a scheduled change is recorded for: who scheduled it,
    else whoever changed the object last."""
    from django.contrib.admin.models import LogEntry

    entries = LogEntry.objects.filter(
        content_type=content_type, object_id=str(object_id)
    ).order_by("-action_time")
    entry = (
        entries.filter(change_message__startswith=MESSAGE_SCHEDULED_PREFIX).first()
        or entries.first()
    )

    return entry.user if entry is not None else None


def _handled(content_type, objects, date_field, messages) -> set[str]:
    """The ids of the objects with a log entry in messages at or after
    their date: the change was already recorded."""
    from django.contrib.admin.models import LogEntry

    if not objects:
        return set()

    earliest = min(getattr(obj, date_field) for obj in objects)
    entries = LogEntry.objects.filter(
        content_type=content_type,
        object_id__in=[str(obj.pk) for obj in objects],
        change_message__in=messages,
        action_time__gte=earliest - datetime.timedelta(seconds=1),
    ).values_list("object_id", "action_time")
    dates = {str(obj.pk): getattr(obj, date_field) for obj in objects}

    return {
        object_id
        for object_id, action_time in entries
        if action_time >= dates[object_id] - datetime.timedelta(seconds=1)
    }


def _sweep_studio(studio, now) -> tuple[int, int]:
    from django.contrib.contenttypes.models import ContentType

    from .signals import record_change

    config = get_publishing(studio)
    model = studio.model
    manager = model._default_manager
    content_type = ContentType.objects.get_for_model(model)
    since = now - CATCH_UP
    published_at = config.published_at
    queryset = manager.all()

    if getattr(studio, "soft_delete", ""):
        queryset = queryset.filter(**{f"{studio.soft_delete}__isnull": True})

    went_live = list(
        queryset.filter(
            **{f"{published_at}__lte": now, f"{published_at}__gt": since}
        ).filter(state_q(config, PUBLISHED, now))
    )
    came_down = []

    if config.unpublish_at:
        unpublish_at = config.unpublish_at
        came_down = list(
            queryset.filter(
                **{
                    f"{unpublish_at}__lte": now,
                    f"{unpublish_at}__gt": since,
                    f"{published_at}__isnull": False,
                }
            )
        )

    done = _handled(
        content_type,
        went_live,
        published_at,
        [MESSAGE_PUBLISHED, MESSAGE_PUBLISHED_ON_SCHEDULE],
    )
    went_live = [obj for obj in went_live if str(obj.pk) not in done]

    if config.unpublish_at:
        done = _handled(
            content_type,
            came_down,
            config.unpublish_at,
            [MESSAGE_UNPUBLISHED_ON_SCHEDULE],
        )
        came_down = [obj for obj in came_down if str(obj.pk) not in done]

    counts = [0, 0]

    for index, (objects, state, action, message, hook) in enumerate(
        (
            (
                went_live,
                PUBLISHED,
                PUBLISHED,
                MESSAGE_PUBLISHED_ON_SCHEDULE,
                "on_publish",
            ),
            (
                came_down,
                EXPIRED,
                "unpublished",
                MESSAGE_UNPUBLISHED_ON_SCHEDULE,
                "on_unpublish",
            ),
        )
    ):
        for obj in objects:
            user = _find_user(content_type, obj.pk)

            if user is None:
                # LogEntry needs a user: content scheduled outside the
                # admin, never changed in it, goes live unrecorded.
                logger.info(
                    "%s %s changed state on schedule with no editor to "
                    "record it for.",
                    model._meta.label,
                    obj.pk,
                )
                continue

            try:
                with transaction.atomic(using=router.db_for_write(model)):
                    if config.status:
                        value = config.status_value(state)
                        model._base_manager.filter(pk=obj.pk).update(
                            **{config.status: value}
                        )
                        setattr(obj, config.status, value)

                    record_change(SimpleNamespace(user=user), obj, action, message)
                    getattr(studio, hook)(None, obj)
            except Exception:
                logger.exception(
                    "Scheduled publishing failed for %s %s.",
                    model._meta.label,
                    obj.pk,
                )
                continue

            counts[index] += 1

    return counts[0], counts[1]


def run_scheduled(now=None) -> dict[str, int]:
    """
    Record the content that went live or expired since the last run:
    the activity log entry, content_changed ("published" and
    "unpublished"), the status field and the studio's hooks. Content
    already went live by its dates; this only does what happens at that
    moment. Run it every minute: Huey does when it is installed, else
    content_studio_publish from cron.
    """
    from django.core.cache import cache

    now = _now(now)
    published = unpublished = 0

    for studio in get_publishing_studios():
        try:
            live_count, down_count = _sweep_studio(studio, now)
        except Exception:
            logger.exception(
                "Scheduled publishing failed for %s.", studio.model._meta.label
            )
            continue

        published += live_count
        unpublished += down_count

    try:
        cache.set(LAST_RUN_CACHE_KEY, now, None)
    except Exception:  # pragma: no cover -- a cache that is down
        logger.warning("Could not store the scheduled publishing run.")

    return {"published": published, "unpublished": unpublished}


def get_last_run():
    from django.core.cache import cache

    try:
        return cache.get(LAST_RUN_CACHE_KEY)
    except Exception:  # pragma: no cover
        return None


# The Huey periodic task, once registered.
_periodic = None


def register_periodic_task(huey=None):
    """
    Run run_scheduled every minute in Huey's consumer when Huey is
    installed and a studio configures publishing.
    """
    global _periodic

    if _periodic is not None:
        return _periodic

    if not get_publishing_studios():
        return None

    from .contrib.backups.huey import close_db, get_huey

    huey = huey if huey is not None else get_huey()

    if huey is None:
        return None

    from huey import crontab

    _periodic = huey.periodic_task(crontab(), name="content_studio.publishing")(
        close_db(scheduled_publishing)
    )
    return _periodic


def scheduled_publishing():
    return run_scheduled()


def register_status() -> None:
    """The sweep on the system status page (harmless without the app)."""
    if not get_publishing_studios():
        return

    from .contrib.status import register_recurring_task

    register_recurring_task(
        "content_studio.publishing",
        _("Scheduled publishing"),
        schedule=_("Every minute"),
        get_last_run=get_last_run,
        group=_("Content Studio"),
    )


def get_status_filter_class():
    from .filters import ListFilter

    class StatusFilter(ListFilter):
        title = _("Status")
        parameter_name = STATUS_FILTER
        options = [(state, STATE_LABELS[state]) for state in STATES]
        multiple = True

        def get_options(self, request):
            from .pending import uses_pending_changes

            config = get_publishing(self.studio)
            states = STATES if config and config.unpublish_at else STATES[:3]
            options = [(state, STATE_LABELS[state]) for state in states]

            if uses_pending_changes(self.studio):
                options.append((PENDING, _("Unpublished changes")))

            return options

        def queryset(self, request, queryset, value):
            config = get_publishing(self.studio)
            values = value if isinstance(value, list) else [value]
            states = [state for state in values if state != PENDING]
            filtered = filter_state(queryset, config, states) if states else None

            if PENDING not in values:
                return filtered

            from .pending import pending_object_ids, uses_pending_changes

            if not uses_pending_changes(self.studio):
                return filtered if filtered is not None else queryset.none()

            pk = queryset.model._meta.pk
            ids = []

            for object_id in pending_object_ids(queryset.model):
                try:
                    ids.append(pk.to_python(object_id))
                except ValidationError:
                    pass

            with_pending = queryset.filter(pk__in=ids)

            return with_pending if filtered is None else filtered | with_pending

    return StatusFilter


def check_field(model, name) -> Optional[str]:
    """Why a publishing date field does not fit, or None."""
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return f"'{name}' is not a field of {model._meta.label}"

    if not isinstance(field, models.DateTimeField):
        return f"'{name}' is not a DateTimeField"

    if not field.null:
        return f"'{name}' must be nullable (null=True)"

    return None


def label(state: str) -> StrOrPromise:
    return STATE_LABELS.get(state, state)
