"""
Notifications about reviews, with content_studio.notifications
installed: a request to review (to the reviewer the submitter picked,
else everyone who may approve it), and the decision (to the
submitter). Each event can be turned off on the settings page.
"""

from django.apps import apps
from django.utils.translation import gettext_lazy as _

REQUESTED = "review.requested"
APPROVED = "review.approved"
CHANGES_REQUESTED = "review.changes_requested"

# The excerpt of a note in a notification.
EXCERPT_LENGTH = 200


def notifications_installed() -> bool:
    return apps.is_installed("content_studio.notifications")


def register_events():
    if not notifications_installed():
        return

    from ..notifications import register_event

    register_event(
        REQUESTED,
        _("Review requests"),
        _("Someone submits content for you to review."),
    )
    register_event(
        APPROVED,
        _("Approved reviews"),
        _("Content you submitted for review is approved."),
    )
    register_event(
        CHANGES_REQUESTED,
        _("Changes requested"),
        _("A reviewer asks for changes to content you submitted."),
    )


def excerpt(text: str) -> str:
    text = " ".join((text or "").split())

    if len(text) <= EXCERPT_LENGTH:
        return text

    return text[: EXCERPT_LENGTH - 1].rstrip() + "…"


def _name(user) -> str:
    if user is None:
        return ""

    return user.get_full_name() or user.get_username()


def notify_review(event, review, target, actor, user_ids) -> None:
    """Notify users of a review event, leaving out the actor and the
    users who turned the event off."""
    if not notifications_installed():
        return

    from django.contrib.auth import get_user_model

    from ..notifications import notify
    from ..notifications.events import get_event
    from ..notifications.permissions import notifications_enabled
    from ..notifications.sending import subscriber_ids

    if not notifications_enabled(type(target)):
        return

    user_ids = {pk for pk in user_ids if pk is not None}

    if actor is not None:
        user_ids.discard(actor.pk)

    user_ids &= subscriber_ids(get_event(event), review.tenant)

    if not user_ids:
        return

    if event == REQUESTED:
        title = (
            _("%(actor)s asked you to review %(object)s")
            if review.reviewer_id
            else _("%(actor)s submitted %(object)s for review")
        )
        note = review.note
    elif event == APPROVED:
        title = _("%(actor)s approved %(object)s")
        note = review.decision_note
    else:
        title = _("%(actor)s requested changes to %(object)s")
        note = review.decision_note

    notify(
        event,
        title=title,
        body="%(excerpt)s",
        params={
            "excerpt": excerpt(note),
            "actor": _name(actor),
            "object": str(target)[:100],
        },
        target=target,
        actor=actor,
        recipients=get_user_model()._default_manager.filter(pk__in=user_ids),
    )
