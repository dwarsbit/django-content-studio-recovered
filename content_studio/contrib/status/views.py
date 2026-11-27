from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ...permissions import IsActiveStaff
from ...settings import cs_settings
from .runner import get_status
from .tasks import get_tasks


class HasStatusPermission(BasePermission):
    """Whoever the admin site's has_status_permission() lets in."""

    def has_permission(self, request, view):
        return bool(cs_settings.ADMIN_SITE.has_status_permission(request))


class StatusViewSet(ViewSet):
    """The system status page."""

    # Explicit, so the project's DEFAULT_PERMISSION_CLASSES never decide.
    permission_classes = [IsActiveStaff, HasStatusPermission]
    renderer_classes = [JSONRenderer]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        admin_site = cs_settings.ADMIN_SITE
        self.authentication_classes = [
            admin_site.token_backend.active_backend.authentication_class
        ]

    def list(self, request):
        """The services with their status, checked at most once a minute."""
        return Response(get_status())

    @action(methods=["post"], detail=False, url_path="refresh")
    def refresh(self, request):
        """Check the services again, now."""
        return Response(get_status(force=True))

    @action(methods=["get"], detail=False, url_path="summary")
    def summary(self, request):
        """The overall status, for the dot on the user menu."""
        status = get_status()

        return Response(
            {"status": status["status"], "checked_at": status["checked_at"]}
        )

    @action(methods=["get"], detail=False, url_path="errors")
    def errors(self, request):
        """The viewer's latest error reports, for the Recent errors card."""
        from ...error_reports.status import get_recent_errors

        return Response(get_recent_errors(request))

    @action(methods=["get"], detail=False, url_path="tasks")
    def tasks(self, request):
        """The pending, finished and recurring tasks."""
        return Response(get_tasks(request))


def set_up_router():
    from ...router import content_studio_router

    content_studio_router.register(
        "api/status", StatusViewSet, basename="content_studio_status"
    )
