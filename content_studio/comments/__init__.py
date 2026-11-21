"""
Internal comments: staff-only comment threads on the objects of the
studios, with replies, resolving and @mentions. An optional app: add
"content_studio.comments" to INSTALLED_APPS. Mentions and replies notify
people through content_studio.notifications when it is installed.

Comments are never public: only users who may view an object see its
comments and may comment.
"""

from django.apps import apps as django_apps

from .signals import comment_added

__all__ = ["add_comment", "comment_added", "comments_enabled", "get_comments"]


def add_comment(obj, author, body, **kwargs):
    """Post a comment on obj; see content_studio.comments.api.add_comment."""
    from .api import add_comment as _add_comment

    return _add_comment(obj, author, body, **kwargs)


def get_comments(obj):
    """The comments on obj, oldest first."""
    from .api import get_comments as _get_comments

    return _get_comments(obj)


def comments_enabled(studio) -> bool:
    """
    Whether a studio's edit page has comments: the app is installed,
    the studio is a ModelStudio and does not opt out with
    comments = False.
    """
    from ..admin import ModelStudio

    return (
        django_apps.is_installed("content_studio.comments")
        and isinstance(studio, ModelStudio)
        and bool(getattr(studio, "comments", True))
    )
