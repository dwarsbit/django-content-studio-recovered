"""
Comments from code: add_comment() posts one, comment_added fires for
every new comment (from the edit page or from code).
"""

from django.contrib.contenttypes.models import ContentType
from django.db import router, transaction

from ..utils import get_tenant_field_name
from .signals import comment_added

MAX_LENGTH = 10_000


def tenant_of(obj) -> str:
    field_name = get_tenant_field_name(type(obj))
    tenant_id = getattr(obj, f"{field_name}_id") if field_name else None

    return "" if tenant_id is None else str(tenant_id)


def add_comment(
    obj,
    author,
    body: str,
    *,
    parent=None,
    mentions=None,
    notify: bool = True,
    kind: str = "",
):
    """
    Post a comment on obj as author (a user, or None for a comment from
    the system). parent makes it a reply in that thread; mentions are
    the users (or user ids) it mentions, who are notified with the
    notifications app installed. kind marks a comment posted by a
    feature, such as "review.submitted" for a review note. Returns the
    Comment.
    """
    from .models import Comment
    from .notifying import notify_comment

    body = (body or "").strip()

    if not body:
        raise ValueError("A comment needs a body.")

    if parent is not None and parent.parent_id is not None:
        # Replies go one level deep: a reply to a reply joins the thread.
        parent = parent.parent

    mention_ids = sorted(
        {getattr(user, "pk", user) for user in (mentions or [])} - {None}
    )
    comment = Comment.objects.create(
        content_type=ContentType.objects.get_for_model(type(obj)),
        object_id=str(obj.pk),
        tenant=tenant_of(obj),
        parent=parent,
        author=author,
        body=body[:MAX_LENGTH],
        mentions=mention_ids,
        kind=kind[:40],
    )

    if notify:
        notify_comment(comment, obj, author)

    transaction.on_commit(
        lambda: comment_added.send(
            sender=Comment, comment=comment, target=obj, author=author
        ),
        using=router.db_for_write(Comment),
    )

    return comment


def get_comments(obj):
    """The comments on obj, oldest first (a queryset of Comment)."""
    from .models import Comment

    return Comment.objects.filter(
        content_type=ContentType.objects.get_for_model(type(obj)),
        object_id=str(obj.pk),
    )
