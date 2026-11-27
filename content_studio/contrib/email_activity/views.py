import logging

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Q
from django.utils.translation import gettext as _
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ...parsers import ObjectJSONParser
from ...permissions import IsActiveStaff
from ...settings import cs_settings
from . import log
from .kinds import TEST, email_kind, kind_label
from .models import SentEmail

logger = logging.getLogger("content_studio.email_activity")

# Emails per page; Load more asks for the next.
LIMIT = 50

# The longest search the list takes.
MAX_QUERY = 200


class HasEmailActivityPermission(BasePermission):
    """Whoever the admin site's has_email_activity_permission() lets in."""

    def has_permission(self, request, view):
        return bool(cs_settings.ADMIN_SITE.has_email_activity_permission(request))


def iso(value):
    return None if value is None else value.isoformat()


def serialize(email: SentEmail) -> dict:
    return {
        "id": email.pk,
        "from_email": email.from_email,
        "to": email.to,
        "cc": email.cc,
        "bcc": email.bcc,
        "reply_to": email.reply_to,
        "subject": email.subject,
        "kind": email.kind,
        "kind_label": kind_label(email.kind),
        "status": email.status,
        "error": email.error or None,
        "backend": email.backend,
        "message_id": email.message_id,
        "attachments": email.attachments,
        "size": email.size,
        "sent_by": str(email.sent_by) if email.sent_by_id else None,
        "created_at": iso(email.created_at),
        "finished_at": iso(email.finished_at),
        "duration": email.duration,
    }


def parse_offset(value) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


class EmailActivityViewSet(ViewSet):
    """The Email activity page: the sent emails and Send test email."""

    # Explicit, so the project's DEFAULT_PERMISSION_CLASSES never decide.
    permission_classes = [IsActiveStaff, HasEmailActivityPermission]
    renderer_classes = [JSONRenderer]
    parser_classes = [ObjectJSONParser]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        admin_site = cs_settings.ADMIN_SITE
        self.authentication_classes = [
            admin_site.token_backend.active_backend.authentication_class
        ]

    def list(self, request):
        from ...password_links import get_email

        params = request.query_params
        kind = params.get("kind")
        query = (params.get("q") or "").strip()[:MAX_QUERY]
        status = params.get("status")
        offset = parse_offset(params.get("offset"))

        emails = SentEmail.objects.all()

        if kind is not None:
            emails = emails.filter(kind=kind)

        if query:
            emails = emails.filter(
                Q(recipients__icontains=query)
                | Q(from_email__icontains=query)
                | Q(subject__icontains=query)
            )

        counts = emails.aggregate(
            all=Count("pk"),
            sent=Count("pk", filter=Q(status=SentEmail.SENT)),
            failed=Count("pk", filter=Q(status=SentEmail.FAILED)),
        )

        if status in (SentEmail.SENT, SentEmail.FAILED):
            emails = emails.filter(status=status)
            total = counts[status]
        else:
            total = counts["all"]

        page = emails.select_related("sent_by")[offset : offset + LIMIT]
        kinds = SentEmail.objects.order_by().values_list("kind", flat=True).distinct()
        sent, failed = log.recent_counts()

        return Response(
            {
                "emails": [serialize(email) for email in page],
                "total": total,
                "offset": offset,
                "limit": LIMIT,
                "counts": counts,
                "kinds": sorted(
                    ({"value": value, "label": kind_label(value)} for value in kinds),
                    key=lambda item: item["label"].lower(),
                ),
                "summary": {
                    "backend": log.delivery_description(),
                    "default_backend": log.default_backend_path(),
                    "sent": sent,
                    "failed": failed,
                    "keep_days": cs_settings.EMAIL_ACTIVITY_KEEP_DAYS,
                    "logging": log.is_logging(),
                    "masked": bool(cs_settings.EMAIL_ACTIVITY_MASK),
                },
                "your_email": get_email(request.user),
            }
        )

    @action(methods=["post"], detail=False, url_path="test")
    def test(self, request):
        """Send a short email through the configured backend, now."""
        from django.core.mail import EmailMessage
        from django.template.loader import render_to_string

        to = str((request.data or {}).get("to") or "").strip()

        try:
            validate_email(to)
        except ValidationError:
            return Response(
                {"to": [_("Enter a valid email address.")]},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        site_title = str(
            getattr(cs_settings.ADMIN_SITE, "site_title", "") or ""
        ).strip()
        context = {
            "site_title": site_title,
            "sender": request.user.get_username(),
        }
        message = EmailMessage(
            subject=_("Test email from %(site)s") % {"site": site_title},
            body=render_to_string("content_studio/email_activity/test.txt", context),
            to=[to],
        )

        try:
            with email_kind(TEST, sent_by=request.user):
                sent = message.send()
        except Exception as exc:
            logger.warning("The test email to %s was not sent.", to, exc_info=True)
            return Response(
                {"detail": log.describe_error(exc)},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if not sent:
            return Response(
                {"detail": _("The email backend did not send it.")},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        logger.info("%s sent a test email to %s.", request.user, to)

        return Response({"detail": _("Test email sent to %(email)s.") % {"email": to}})


def set_up_router():
    from ...router import content_studio_router

    content_studio_router.register(
        "api/email-activity",
        EmailActivityViewSet,
        basename="content_studio_email_activity",
    )
