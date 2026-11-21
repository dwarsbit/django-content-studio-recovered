"""
Notifications about comments, with content_studio.notifications
installed: a mention, a reply in a thread you are in, and a comment on
an object you follow. Each person gets one notification per comment,
the first of those that applies, and only when they are subscribed to
that event (all three are on by default).
"""

from django.apps import apps
from django.utils.translation import gettext_lazy as _

MENTION = "comments.mention"
REPLY = "comments.reply"
COMMENT = "comments.comment"

# The excerpt of the comment in a notification.
EXCERPT_LENGTH = 200


def notifications_installed() -> bool:
    return apps.is_installed("content_studio.notifications")


def register_events():
    if not notifications_installed():
        return

    from ..notifications import register_event

    register_event(
        MENTION,
        _("Mentions in comments"),
        _("Someone mentions you in a comment."),
    )
    register_event(
        REPLY,
        _("Replies to comments"),
        _("Someone replies in a comment thread you are in."),
    )
    register_event(
        COMMENT,
        _("Comments on content you follow"),
        _("Someone comments on an object you follow."),
    )


def excerpt(text: str) -> str:
    text = " ".join(text.split())

    if len(text) <= EXCERPT_LENGTH:
        return text

    return text[: EXCERPT_LENGTH - 1].rstrip() + "…"


def notify_comment(comment, target, actor, mentioned_ids=None) -> None:
    """
    Notify about a new comment (or the people newly mentioned in an
    edited one, with mentioned_ids): the mentioned users, then the
    others in the thread, then the object's followers.
    """
    if not notifications_installed():
        return

    from django.contrib.auth import get_user_model
    from django.contrib.contenttypes.models import ContentType

    from ..notifications import notify
    from ..notifications.events import get_event
    from ..notifications.models import Follow
    from ..notifications.permissions import notifications_enabled
    from ..notifications.sending import subscriber_ids
    from .models import Comment

    if not notifications_enabled(type(target)):
        return

    tenant = comment.tenant
    notified = {actor.pk} if actor is not None else set()
    mentioned = set(comment.mentions if mentioned_ids is None else mentioned_ids)
    groups = [(MENTION, mentioned)]

    if mentioned_ids is None:
        thread = comment.parent or comment
        in_thread = set(
            Comment.objects.filter(pk=thread.pk).values_list("author_id", flat=True)
        ) | set(thread.replies.values_list("author_id", flat=True))
        followers = set(
            Follow.objects.filter(
                content_type=ContentType.objects.get_for_model(target),
                object_id=str(target.pk),
            ).values_list("user_id", flat=True)
        )
        groups += [
            (REPLY, in_thread if comment.parent_id else set()),
            (COMMENT, followers),
        ]

    titles = {
        MENTION: _("%(actor)s mentioned you on %(object)s"),
        REPLY: _("%(actor)s replied to a comment on %(object)s"),
        COMMENT: _("%(actor)s commented on %(object)s"),
    }
    params = {
        "excerpt": excerpt(comment.body),
        "actor": (
            (actor.get_full_name() or actor.get_username()) if actor is not None else ""
        ),
        "object": str(target)[:100],
    }
    User = get_user_model()

    for event, user_ids in groups:
        user_ids = {pk for pk in user_ids if pk is not None} - notified

        if not user_ids:
            continue

        # Explicit recipients skip the subscriptions: keep the users
        # who did not turn the event off.
        user_ids &= subscriber_ids(get_event(event), tenant)
        notified |= user_ids

        if user_ids:
            notify(
                event,
                title=titles[event],
                body="%(excerpt)s",
                params=params,
                target=target,
                actor=actor,
                recipients=User._default_manager.filter(pk__in=user_ids),
            )
