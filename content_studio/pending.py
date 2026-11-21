"""
Unpublished changes: edits to published content that stay out of sight
until they are published.

A studio turns them on with Publishing(..., pending_changes=True). Saving
a published object then validates the edit as a save would, but stores
the changed fields apart from the object (the history app's
PendingChanges) instead of writing them: the site keeps showing the
published version. The edit page shows the object with the unpublished
changes, and:

- Publish changes saves them to the object the regular way (the model's
  validation, the studio's save hooks, the activity log, history and
  content_changed), then removes them;
- Discard removes them;
- unpublishing or scheduling the object again (it is no longer live)
  saves them to it first, so the draft keeps them.

Only the object's own fields are held back: inline rows save through
their own pages and go live as before.
"""

import json
import posixpath
from typing import Any, Optional

from django.apps import apps
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from .publishing import PUBLISHED, get_publishing, get_state

__all__ = [
    "discard",
    "get_pending",
    "holds_changes",
    "overlay",
    "publish",
    "uses_pending_changes",
]

# The activity log's messages, stored as written like "Published.".
MESSAGE_SAVED = "Saved unpublished changes."
MESSAGE_DISCARDED = "Discarded the unpublished changes."

# How a new file is kept in PendingChanges.data: its name in the
# field's storage, saved there when the changes were.
STORED_FILE = "stored"


def uses_pending_changes(studio) -> bool:
    """Whether the studio keeps edits to published objects unpublished."""
    config = get_publishing(studio)

    return bool(
        config
        and config.pending_changes
        and apps.is_installed("content_studio.history")
    )


def holds_changes(studio, obj) -> bool:
    """Whether saving obj now keeps the changes unpublished: the studio
    uses pending changes and the object is live."""
    if not uses_pending_changes(studio) or obj is None or obj.pk is None:
        return False

    return get_state(get_publishing(studio), obj) == PUBLISHED


def _model():
    from .history.models import PendingChanges

    return PendingChanges


def get_pending(obj):
    """The object's unpublished changes, or None."""
    if not apps.is_installed("content_studio.history") or obj.pk is None:
        return None

    return (
        _model()
        .objects.filter(
            content_type=ContentType.objects.get_for_model(obj),
            object_id=str(obj.pk),
        )
        .select_related("edited_by")
        .first()
    )


def pending_object_ids(model) -> set[str]:
    """The ids of the model's objects with unpublished changes, for the
    list's Status column."""
    if not apps.is_installed("content_studio.history"):
        return set()

    return set(
        _model()
        .objects.filter(content_type=ContentType.objects.get_for_model(model))
        .values_list("object_id", flat=True)
    )


def _plain(value):
    """A value as stored and compared: plain JSON."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _user_name(user) -> Optional[str]:
    if user is None:
        return None

    return user.get_full_name() or user.get_username()


def serialize(pending, live: dict) -> Optional[dict[str, Any]]:
    """What the edit page shows of the unpublished changes: the changed
    fields, who saved them last and when, and the published values of
    those fields, for Compare."""
    if pending is None:
        return None

    return {
        "fields": list(pending.fields),
        "edited_by": _user_name(pending.edited_by),
        "edited_at": pending.edited_at.isoformat(),
        "live": {name: live.get(name) for name in pending.fields},
    }


def overlay(data: dict, pending) -> dict:
    """An object's representation with its unpublished changes."""
    if pending is None:
        return data

    return {**data, **{name: pending.values.get(name) for name in pending.fields}}


def _store_file(model_field, instance, upload) -> str:
    """Save a new file to the field's storage now, under the name a save
    would give it: the temporary upload expires before the changes
    may be published."""
    name = model_field.generate_filename(instance, posixpath.basename(upload.name))
    upload.file.seek(0)

    return model_field.storage.save(name, upload.file, max_length=model_field.max_length)


def _is_stored(value) -> bool:
    return isinstance(value, dict) and STORED_FILE in value


def _delete_file(model, name, value):
    """Remove a new file kept for unpublished changes that were dropped."""
    try:
        model._meta.get_field(name).storage.delete(value[STORED_FILE])
    except Exception:  # A file that is gone already, or no such field.
        pass


def _delete_stored_files(pending):
    """Remove the new files kept for unpublished changes."""
    model = pending.content_type.model_class()

    if model is None:
        return

    for name, value in pending.data.items():
        if _is_stored(value):
            _delete_file(model, name, value)


def save(request, studio, serializer, instance):
    """
    Keep a validated edit of a live object as its unpublished changes:
    the model's validation runs on the values as a save would, and the
    fields that differ from the published object are stored. A field
    that matches the published object again is no longer a change;
    without changes left, the unpublished changes are removed.

    Returns the changes, or None when none are left.
    """
    from .uploads import TemporaryUpload, discard_upload

    candidate = serializer.check_values(instance)
    live = serializer.to_representation(instance)
    pending = get_pending(instance)
    data = dict(pending.data) if pending else {}
    values = dict(pending.values) if pending else {}
    fields = list(pending.fields) if pending else []

    for name, value in serializer.validated_data.items():
        field = serializer.fields[name]
        earlier = data.get(name)

        if isinstance(value, TemporaryUpload):
            model_field = instance._meta.get_field(name)
            stored = _store_file(model_field, candidate, value)
            discard_upload(value)
            new_data = {STORED_FILE: stored}
            new_value = {
                "name": posixpath.basename(stored),
                "url": model_field.storage.url(stored),
            }
            changed = True
        else:
            new_data = _plain(serializer.initial_data.get(name))
            new_value = (
                _plain(field.to_representation(value)) if value is not None else None
            )
            changed = new_value != _plain(live.get(name))

        # A new file kept for an earlier save that this one replaces.
        if _is_stored(earlier) and earlier != new_data:
            _delete_file(instance, name, earlier)

        if not changed:
            if name in fields:
                fields.remove(name)
                data.pop(name, None)
                values.pop(name, None)
            continue

        if name not in fields:
            fields.append(name)

        data[name] = new_data
        values[name] = new_value

    Model = _model()
    content_type = ContentType.objects.get_for_model(instance)

    if not fields:
        if pending is not None:
            pending.delete()

        return None

    # Field order, as the form has them.
    order = list(serializer.fields)
    fields.sort(key=lambda name: order.index(name) if name in order else len(order))
    now = timezone.now()

    pending, _created = Model.objects.update_or_create(
        content_type=content_type,
        object_id=str(instance.pk),
        defaults={
            "fields": fields,
            "data": data,
            "values": values,
            "edited_by": request.user,
            "edited_at": now,
        },
        create_defaults={
            "fields": fields,
            "data": data,
            "values": values,
            "created_by": request.user,
            "edited_by": request.user,
            "created_at": now,
            "edited_at": now,
        },
    )

    LogEntry.objects.create(
        user=request.user,
        action_flag=CHANGE,
        content_type=content_type,
        object_id=instance.pk,
        object_repr=str(instance)[:200],
        change_message=MESSAGE_SAVED,
    )

    return pending


def split_data(pending) -> tuple[dict, dict]:
    """The unpublished changes as a save takes them: the values for the
    serializer, and the new files' stored names to set on the object."""
    values = {}
    files = {}

    for name, value in pending.data.items():
        if _is_stored(value):
            files[name] = value[STORED_FILE]
        else:
            values[name] = value

    return values, files


def discard(request, instance, pending=None, log=True) -> bool:
    """Remove the object's unpublished changes and the new files kept
    for them. Returns whether there were any."""
    pending = pending or get_pending(instance)

    if pending is None:
        return False

    _delete_stored_files(pending)
    pending.delete()

    if log:
        LogEntry.objects.create(
            user=request.user,
            action_flag=CHANGE,
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            object_repr=str(instance)[:200],
            change_message=MESSAGE_DISCARDED,
        )

    return True


def publish(viewset, instance) -> bool:
    """Save the object's unpublished changes to it the regular way, then
    remove them. Returns whether there were any. Raises the serializer's
    ValidationError when they no longer validate (a unique value taken
    in the meantime)."""
    pending = get_pending(instance)

    if pending is None:
        return False

    values, files = split_data(pending)
    serializer = viewset.get_serializer(instance, data=values, partial=True)
    serializer.is_valid(raise_exception=True)
    viewset.perform_update(serializer, files=files, keep_pending=True)
    pending.delete()

    return True
