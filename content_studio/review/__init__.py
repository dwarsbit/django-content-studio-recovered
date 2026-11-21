"""
Review and approval: an opt-in step in front of Publish on studios with
publishing. An editor submits an object for review; someone who may
publish it approves it (publishing or scheduling it in the same step)
or requests changes with a note.

    class ArticleStudio(ModelStudio):
        publishing = Publishing("published_at")
        review = True  # or Review(required=True)

An optional app: add "content_studio.review" to INSTALLED_APPS. Review
requests are kept in its table, with who submitted and decided and the
values that were approved.
"""

from typing import Optional

from django.apps import apps as django_apps

from .signals import review_decided, review_submitted

__all__ = [
    "Review",
    "get_review",
    "review_decided",
    "review_enabled",
    "review_submitted",
]


class Review:
    """
    The review configuration of a studio.

    required=True makes publishers go through review too: the object
    is only published by approving a review request. self_approval=True
    lets someone who may publish approve their own request.
    """

    def __init__(self, *, required: bool = False, self_approval: bool = False):
        self.required = bool(required)
        self.self_approval = bool(self_approval)

    def __repr__(self):
        return (
            f"Review(required={self.required!r}, self_approval={self.self_approval!r})"
        )

    def serialize(self) -> dict:
        return {"required": self.required, "self_approval": self.self_approval}


def get_review(studio) -> Optional[Review]:
    """A studio's review configuration, or None without one."""
    value = getattr(studio, "review", None)

    if isinstance(value, Review):
        return value

    if value is True:
        return Review()

    return None


def review_enabled(studio) -> bool:
    """
    Whether a studio's objects go through review: the app is
    installed, and the studio has publishing and a review
    configuration.
    """
    from ..publishing import get_publishing

    return (
        django_apps.is_installed("content_studio.review")
        and get_review(studio) is not None
        and get_publishing(studio) is not None
    )
