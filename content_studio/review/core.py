"""
What review does: submitting, withdrawing and deciding, and what the
edit page and the list show of it. The content endpoint
(content/<model>/<id>/review) calls these.
"""

import hashlib
import json
from typing import Any, Optional

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import get_review, review_enabled
from .models import APPROVED, CHANGES_REQUESTED, OPEN, WITHDRAWN, ReviewRequest
from .signals import review_decided, review_submitted

# The activity log's messages, stored as written like "Published.".
MESSAGE_SUBMITTED = "Submitted for review."
MESSAGE_WITHDRAWN = "Withdrew the review request."
MESSAGE_APPROVED = "Approved."
MESSAGE_CHANGES_REQUESTED = "Requested changes."

# The kinds of the comments review posts with the comments app.
COMMENT_SUBMITTED = "review.submitted"
COMMENT_APPROVED = "review.approved"
COMMENT_CHANGES_REQUESTED = "review.changes_requested"

# How many people the reviewer picker lists.
MAX_REVIEWERS = 100

MAX_NOTE_LENGTH = 10_000


def _content_type(obj):
    return ContentType.objects.get_for_model(type(obj))


def tenant_of(obj) -> str:
    from ..utils import get_tenant_field_name

    field_name = get_tenant_field_name(type(obj))
    tenant_id = getattr(obj, f"{field_name}_id") if field_name else None

    return "" if tenant_id is None else str(tenant_id)


def get_current(obj) -> Optional[ReviewRequest]:
    """The object's current review request (in review or with changes
    requested), or None."""
    if obj is None or obj.pk is None:
        return None

    return (
        ReviewRequest.objects.filter(
            content_type=_content_type(obj),
            object_id=str(obj.pk),
            closed_at__isnull=True,
        )
        .select_related("submitted_by", "reviewer", "decided_by")
        .first()
    )


def current_statuses(model) -> dict[str, dict[str, Any]]:
    """The current review requests of a model's objects, by object id:
    their status and picked reviewer, for the list."""
    rows = ReviewRequest.objects.filter(
        content_type=ContentType.objects.get_for_model(model),
        closed_at__isnull=True,
    ).values_list("object_id", "status", "reviewer_id", "submitted_by_id")

    return {
        object_id: {
            "status": status,
            "reviewer_id": reviewer_id,
            "submitted_by_id": submitted_by_id,
        }
        for object_id, status, reviewer_id, submitted_by_id in rows
    }


def last_approved(obj) -> Optional[ReviewRequest]:
    return (
        ReviewRequest.objects.filter(
            content_type=_content_type(obj),
            object_id=str(obj.pk),
            status=APPROVED,
        )
        .filter(approved_snapshot__isnull=False)
        .first()
    )


def comparable(value):
    """
    A value as review compares it: a related object as its id, since
    the edit page's representation of one also holds display text that
    changes with other objects (such as a category's article count).
    """
    if isinstance(value, dict):
        if "id" in value and "__str__" in value:
            return value["id"]

        return {key: comparable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [comparable(item) for item in value]

    return value


def fingerprint(snapshot: Optional[dict]) -> str:
    """The version of an object's values: changes whenever a value does."""
    data = json.dumps(comparable(snapshot or {}), sort_keys=True, default=str)

    return hashlib.sha256(data.encode()).hexdigest()[:20]


def _log(request, obj, message):
    LogEntry.objects.create(
        user=request.user,
        action_flag=CHANGE,
        content_type=_content_type(obj),
        object_id=obj.pk,
        object_repr=str(obj)[:200],
        change_message=message,
    )


def _post_comment(studio, obj, user, body, kind):
    """Post a review note as a comment, with the comments app."""
    from django.apps import apps

    if not body or not apps.is_installed("content_studio.comments"):
        return

    from ..comments import comments_enabled

    if not comments_enabled(studio):
        return

    from ..comments.api import add_comment

    # Review notifies on its own events.
    add_comment(obj, user, body, kind=kind, notify=False)


# Who may do what.


def user_request(user, tenant: str = ""):
    """A request as another user would make it, to ask the studio's
    permission checks about them."""
    from django.http import HttpRequest

    request = HttpRequest()
    request.method = "GET"
    request.user = user

    if tenant:
        request.META["HTTP_X_DCS_TENANT"] = tenant

    return request


def may_approve(studio, request, obj, review: Optional[ReviewRequest]) -> bool:
    """Whether the request may approve or request changes: Can publish
    on the object, and not the submitter unless self_approval."""
    if review is None or review.status != OPEN:
        return False

    if not studio.has_publish_permission(request, obj):
        return False

    config = get_review(studio)

    return bool(config and config.self_approval) or (
        review.submitted_by_id != request.user.pk
    )


def may_withdraw(studio, request, obj, review: Optional[ReviewRequest]) -> bool:
    """The submitter, or someone who may publish the object."""
    if review is None:
        return False

    return review.submitted_by_id == request.user.pk or bool(
        studio.has_publish_permission(request, obj)
    )


def may_submit(studio, request, obj) -> bool:
    return bool(studio.has_change_permission(request, obj))


def get_reviewers(studio, obj, tenant: str = "", exclude=None):
    """The active staff users who may approve requests on obj: Can
    publish on the object (the studio's has_publish_permission)."""
    from django.contrib.auth.models import Permission

    from ..publishing import get_codename

    User = get_user_model()
    model = studio.model
    permission = Permission.objects.filter(
        content_type=ContentType.objects.get_for_model(model, for_concrete_model=False),
        codename=get_codename(model),
    ).first()
    query = Q(is_superuser=True)

    if permission is not None:
        query |= Q(user_permissions=permission) | Q(groups__permissions=permission)

    users = (
        User._default_manager.filter(is_active=True, is_staff=True)
        .filter(query)
        .distinct()
        .order_by(User.USERNAME_FIELD)
    )

    if exclude is not None:
        users = users.exclude(pk=exclude.pk)

    result = []

    for user in users[: MAX_REVIEWERS * 2]:
        try:
            if studio.has_publish_permission(user_request(user, tenant), obj):
                result.append(user)
        except Exception:
            continue

        if len(result) == MAX_REVIEWERS:
            break

    return result


def reviewer_ids(studio, request, obj, review) -> set:
    """Who is asked to review: the picked reviewer, else everyone who
    may approve (the studio's get_reviewers)."""
    if review.reviewer_id:
        return {review.reviewer_id}

    config = get_review(studio)
    exclude = None if (config and config.self_approval) else review.submitted_by
    users = studio.get_reviewers(request, obj)

    if users is None:
        users = get_reviewers(studio, obj, review.tenant, exclude=exclude)

    return {
        getattr(user, "pk", user)
        for user in users
        if exclude is None or getattr(user, "pk", user) != exclude.pk
    }


# Changes.


class ReviewError(Exception):
    """A review change that does not fit; message is for the editor."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def _note(value) -> str:
    note = value.strip() if isinstance(value, str) else ""

    return note[:MAX_NOTE_LENGTH]


def submit(studio, request, obj, *, snapshot, live, note="", reviewer=None):
    """Submit obj for review. Closes a request with changes requested;
    refuses while one is open."""
    from .notifying import REQUESTED, notify_review

    current = get_current(obj)
    now = timezone.now()

    if current is not None and current.status == OPEN:
        from django.utils.translation import gettext as _

        raise ReviewError(_("This object is already in review."))

    with transaction.atomic():
        if current is not None:
            current.closed_at = now
            current.save(update_fields=["closed_at"])

        review = ReviewRequest.objects.create(
            content_type=_content_type(obj),
            object_id=str(obj.pk),
            object_repr=str(obj)[:200],
            tenant=tenant_of(obj),
            live=live,
            submitted_by=request.user,
            reviewer=reviewer,
            note=_note(note),
            snapshot=snapshot or {},
            version=fingerprint(snapshot),
        )
        _log(request, obj, MESSAGE_SUBMITTED)
        _post_comment(studio, obj, request.user, review.note, COMMENT_SUBMITTED)
        notify_review(
            REQUESTED,
            review,
            obj,
            request.user,
            reviewer_ids(studio, request, obj, review),
        )
        studio.on_submit_for_review(request, obj, review)
        transaction.on_commit(
            lambda: review_submitted.send(
                sender=ReviewRequest, request=request, review=review, target=obj
            )
        )

    return review


def withdraw(studio, request, obj, review, log=True):
    """Close the current request without a decision."""
    review.status = WITHDRAWN
    review.closed_at = timezone.now()
    review.decided_by = request.user
    review.decided_at = review.closed_at
    review.save(update_fields=["status", "closed_at", "decided_by", "decided_at"])

    if log:
        _log(request, obj, MESSAGE_WITHDRAWN)

    return review


def request_changes(studio, request, obj, review, note):
    from .notifying import CHANGES_REQUESTED as EVENT
    from .notifying import notify_review

    review.status = CHANGES_REQUESTED
    review.decided_by = request.user
    review.decided_at = timezone.now()
    review.decision_note = _note(note)
    review.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    _log(request, obj, MESSAGE_CHANGES_REQUESTED)
    _post_comment(
        studio, obj, request.user, review.decision_note, COMMENT_CHANGES_REQUESTED
    )
    notify_review(EVENT, review, obj, request.user, {review.submitted_by_id})
    studio.on_review(request, obj, review)
    transaction.on_commit(
        lambda: review_decided.send(
            sender=ReviewRequest, request=request, review=review, target=obj
        )
    )

    return review


def approve(studio, request, obj, review, *, note, snapshot):
    """Record an approval; the caller publishes or schedules the
    object in the same transaction."""
    from .notifying import APPROVED as EVENT
    from .notifying import notify_review

    now = timezone.now()
    review.status = APPROVED
    review.decided_by = request.user
    review.decided_at = now
    review.closed_at = now
    review.decision_note = _note(note)
    review.approved_snapshot = snapshot
    review.save(
        update_fields=[
            "status",
            "decided_by",
            "decided_at",
            "closed_at",
            "decision_note",
            "approved_snapshot",
        ]
    )
    _log(request, obj, MESSAGE_APPROVED)
    _post_comment(studio, obj, request.user, review.decision_note, COMMENT_APPROVED)
    notify_review(EVENT, review, obj, request.user, {review.submitted_by_id})
    studio.on_review(request, obj, review)
    transaction.on_commit(
        lambda: review_decided.send(
            sender=ReviewRequest, request=request, review=review, target=obj
        )
    )

    return review


def close_on_publish(studio, request, obj, *, snapshot=None):
    """Publishing an object some other way (Publish, Schedule, Publish
    changes) settles its current request: an open one counts as
    approved by the publisher, one with changes requested is closed."""
    if not review_enabled(studio):
        return None

    review = get_current(obj)

    if review is None:
        return None

    if review.status == OPEN:
        return approve(studio, request, obj, review, note="", snapshot=snapshot)

    review.closed_at = timezone.now()
    review.save(update_fields=["closed_at"])

    return review


# What the admin shows.


def describe(user, request):
    if user is None:
        return None

    from ..presence import describe_user

    return describe_user(user, request)


def serialize(studio, request, obj, review: Optional[ReviewRequest]):
    """The current request, for the edit page's Publishing card."""
    if review is None:
        return None

    return {
        "id": review.pk,
        "status": review.status,
        "live": review.live,
        "submitted_by": describe(review.submitted_by, request),
        "submitted_at": review.submitted_at.isoformat(),
        "reviewer": describe(review.reviewer, request),
        "note": review.note,
        "decided_by": describe(review.decided_by, request),
        "decided_at": review.decided_at.isoformat() if review.decided_at else None,
        "decision_note": review.decision_note,
        "mine": review.submitted_by_id == request.user.pk,
        "can_approve": may_approve(studio, request, obj, review),
        "can_withdraw": may_withdraw(studio, request, obj, review),
    }


def changed_fields(before: Optional[dict], after: dict) -> list[str]:
    if before is None:
        return []

    names = list(after) + [name for name in before if name not in after]

    return [
        name
        for name in names
        if comparable(before.get(name)) != comparable(after.get(name))
    ]
