"""
The review queue dashboard widget: what waits for the editor's review,
or, for editors who do not review, their own requests. Add it to the
site's dashboard yourself.
"""

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _

from ..dashboard import DashboardWidget

__all__ = ["ReviewQueue"]


class ReviewQueue(DashboardWidget):
    """
    For someone who may approve: the requests waiting for their review
    (asked of them or of nobody in particular), oldest first. For
    others: their own requests in review or with changes requested,
    newest first.
    """

    widget_type = "ReviewQueue"
    name = "ReviewQueue"
    col_span = 4

    def __init__(self, title=None, description=None, limit=8, widget_id=None):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive whole number.")

        self.title = title
        self.description = description
        self.limit = min(limit, 50)
        super().__init__(widget_id)

    def get_data(self, request) -> Any:
        from django.db.models import Q

        from ..settings import cs_settings
        from ..utils import get_tenant_field_name
        from . import get_review, review_enabled
        from .core import describe
        from .models import OPEN, ReviewRequest

        tenant = request.headers.get("x-dcs-tenant", "") or ""
        reviewing = Q(pk__in=[])
        mine = Q(pk__in=[])
        models = {}

        for model, studio in cs_settings.ADMIN_SITE._registry.items():
            if not review_enabled(studio) or not studio.has_view_permission(request):
                continue

            content_type = ContentType.objects.get_for_model(model)
            target = Q(content_type=content_type)

            if get_tenant_field_name(model):
                target &= Q(tenant=tenant) if tenant else Q(pk__in=[])

            models[content_type.pk] = model
            mine |= target & Q(submitted_by=request.user)

            if studio.has_publish_permission(request):
                waiting = (
                    target
                    & Q(status=OPEN)
                    & Q(Q(reviewer=request.user) | Q(reviewer__isnull=True))
                )

                if not get_review(studio).self_approval:
                    waiting &= ~Q(submitted_by=request.user)

                reviewing |= waiting

        current = ReviewRequest.objects.filter(closed_at__isnull=True).select_related(
            "submitted_by", "reviewer"
        )
        can_review = any(
            studio.has_publish_permission(request)
            for model, studio in cs_settings.ADMIN_SITE._registry.items()
            if model in models.values()
        )

        if can_review:
            queryset = current.filter(reviewing).order_by("submitted_at", "pk")
            title = _("Waiting for your review")
            description = _("Submitted for review, oldest first")
        else:
            queryset = current.filter(mine).order_by("-submitted_at", "-pk")
            title = _("Your review requests")
            description = _("In review or with changes requested")

        total = queryset.count()
        results = []

        for review in queryset[: self.limit]:
            model = models[review.content_type_id]
            results.append(
                {
                    "id": review.pk,
                    "model": model._meta.label_lower,
                    "model_name": str(model._meta.verbose_name),
                    "object_id": review.object_id,
                    "title": review.object_repr,
                    "status": review.status,
                    "live": review.live,
                    "submitted_by": describe(review.submitted_by, request),
                    "submitted_at": review.submitted_at.isoformat(),
                    "reviewer": describe(review.reviewer, request),
                }
            )

        return {
            "title": str(self.title or title),
            "description": str(self.description or description),
            "mode": "review" if can_review else "mine",
            "total": total,
            "results": results,
        }
