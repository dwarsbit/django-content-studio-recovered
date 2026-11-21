from django.db import models
from django.utils import timezone

__all__ = [
    "PublishableQuerySet",
    "SingletonManager",
    "SoftDeletableManager",
    "SoftDeletableQuerySet",
]


class SingletonManager(models.Manager):
    def get(self, *args, **kwargs):
        """
        Get will return the singleton instance if it exists and None otherwise.
        """
        return super().first()

    def create(self, **kwargs):
        """
        Creates the singleton if it doesn't already exist.
        Otherwise updates the existing instance.
        """
        singleton = self.get()

        if not singleton:
            return super().create(**kwargs)

        for name, value in kwargs.items():
            setattr(singleton, name, value)

        singleton.save()

        return singleton


class SoftDeletableQuerySet(models.QuerySet):
    def delete(self):
        """
        Soft-deletes every instance in the queryset: stamps removed_at
        instead of removing rows.
        """
        count = self.update(removed_at=timezone.now())
        return count, {self.model._meta.label: count}


class SoftDeletableManager(models.Manager):
    def get_queryset(self):
        return SoftDeletableQuerySet(self.model, using=self._db).filter(
            removed_at__isnull=True
        )


class PublishableQuerySet(models.QuerySet):
    """
    The queryset of PublishableModel: the objects in each publishing
    state, now or at a given time.

        Article.objects.live()
    """

    def _config(self):
        from .publishing import Publishing

        return Publishing(
            "published_at",
            unpublish_at="unpublish_at",
        )

    def live(self, now=None):
        """The published objects: what a site shows."""
        from .publishing import PUBLISHED, state_q

        return self.filter(state_q(self._config(), PUBLISHED, now))

    def drafts(self):
        from .publishing import DRAFT, state_q

        return self.filter(state_q(self._config(), DRAFT))

    def scheduled(self, now=None):
        from .publishing import SCHEDULED, state_q

        return self.filter(state_q(self._config(), SCHEDULED, now))

    def expired(self, now=None):
        from .publishing import EXPIRED, state_q

        return self.filter(state_q(self._config(), EXPIRED, now))
