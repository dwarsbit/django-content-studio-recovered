from collections import defaultdict

from django.apps import apps
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from ...dashboard.activity_log import (
    tenant_scoped_models,
    viewable_content_type_ids,
    visible_entries,
)
from ...export import (
    CSV,
    XLSX,
    get_export_formats,
    rows_csv_response,
    rows_xlsx_response,
)
from ...permissions import IsActiveStaff
from ...settings import cs_settings
from . import entries as timeline
from .models import SignInEvent
from .recording import describe_user_agent

# Items per page; Load more asks for the next.
LIMIT = 50

# Items an export reads per query, and holds at most.
EXPORT_BATCH = 500
EXPORT_MAX = 100_000


class HasAuditLogPermission(BasePermission):
    """Whoever the admin site's has_audit_log_permission() lets in."""

    def has_permission(self, request, view):
        return bool(cs_settings.ADMIN_SITE.has_audit_log_permission(request))


def iso(value):
    return None if value is None else value.isoformat()


def user_data(user):
    if user is None:
        return None

    return {"id": user.pk, "username": user.get_username(), "label": str(user)}


def entry_action(entry) -> str:
    try:
        return entry.content_studio_action.action
    except LogEntry.content_studio_action.RelatedObjectDoesNotExist:
        return timeline.FLAG_ACTIONS.get(entry.action_flag, "updated")


def entry_message(entry) -> str:
    # An empty list of changes reads "No fields changed." in Django; it
    # says nothing an entry does not already say.
    if entry.change_message.strip() in ("", "[]"):
        return ""

    return str(entry.get_change_message())


def model_label(content_type) -> str:
    return f"{content_type.app_label}.{content_type.model}"


def model_name(content_type) -> str:
    model = content_type.model_class()

    return str(model._meta.verbose_name) if model else content_type.model


def existing_objects(entries) -> set[tuple[int, str]]:
    """(content type id, object id) of the entries whose object exists."""
    wanted = defaultdict(set)

    for entry in entries:
        wanted[entry.content_type_id].add(entry.object_id)

    found = set()

    for content_type_id, object_ids in wanted.items():
        model = ContentType.objects.get_for_id(content_type_id).model_class()

        if model is None:
            continue

        pks = []

        for object_id in object_ids:
            try:
                pks.append(model._meta.pk.to_python(object_id))
            except DjangoValidationError:
                continue

        # The base manager: trashed objects still exist.
        for pk in model._base_manager.filter(pk__in=pks).values_list("pk", flat=True):
            found.add((content_type_id, str(pk)))

    return found


def versioned(entries) -> set[int]:
    """The ids of the entries the history app kept a version with."""
    if not entries or not apps.is_installed("content_studio.history"):
        return set()

    from ...history.models import Version

    return set(
        Version.objects.filter(
            log_entry__in=[entry.pk for entry in entries]
        ).values_list("log_entry_id", flat=True)
    )


def serialize_page(items) -> list[dict]:
    changes = [item.obj for item in items if item.source == timeline.CHANGES]
    existing = existing_objects(changes)
    with_version = versioned(changes)

    return [
        (
            serialize_change(item.obj, existing, with_version)
            if item.source == timeline.CHANGES
            else serialize_sign_in(item.obj)
        )
        for item in items
    ]


def serialize_change(entry, existing, with_version) -> dict:
    return {
        "id": f"change-{entry.pk}",
        "kind": timeline.CHANGES,
        "entry_id": entry.pk,
        "action": entry_action(entry),
        "time": iso(entry.action_time),
        "user": user_data(entry.user),
        "model": model_label(entry.content_type),
        "model_name": model_name(entry.content_type),
        "object_id": entry.object_id,
        "object_repr": entry.object_repr,
        "object_exists": (entry.content_type_id, str(entry.object_id)) in existing,
        "message": entry_message(entry),
        "has_version": entry.pk in with_version,
    }


def serialize_sign_in(event) -> dict:
    return {
        "id": f"sign-in-{event.pk}",
        "kind": timeline.SIGN_INS,
        "action": event.kind,
        "time": iso(event.created_at),
        "user": user_data(event.user),
        "username": event.username,
        "method": event.method,
        "reason": event.reason,
        "ip_address": event.ip_address,
        "browser": describe_user_agent(event.user_agent),
        "user_agent": event.user_agent,
    }


class AuditLogViewSet(ViewSet):
    """
    The Audit log page: changes made in the admin and sign-ins, newest
    first. Changes are limited to the models the user may view and, on
    tenant-scoped models, to objects in the request's tenant.
    """

    permission_classes = [IsActiveStaff, HasAuditLogPermission]
    renderer_classes = [JSONRenderer]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        admin_site = cs_settings.ADMIN_SITE
        self.authentication_classes = [
            admin_site.token_backend.active_backend.authentication_class
        ]

    def list(self, request):
        params = request.query_params
        filters = timeline.parse_filters(params)
        cursor = None

        if params.get("after"):
            cursor = timeline.Key.decode(params["after"])

            if cursor is None:
                raise ValidationError({"after": [_("This cursor is not valid.")]})

        items, next_key = timeline.get_page(request, filters, cursor, LIMIT)
        data = {
            "entries": serialize_page(items),
            "next": next_key.encode() if next_key else None,
            "limit": LIMIT,
        }

        # What the filters offer, on the first page only.
        if cursor is None:
            data["options"] = self.get_options(request)

        return Response(data)

    def get_options(self, request) -> dict:
        content_types = ContentType.objects.filter(
            pk__in=viewable_content_type_ids(request)
        )
        models = sorted(
            (
                {"value": model_label(content_type), "label": model_name(content_type)}
                for content_type in content_types
            ),
            key=lambda option: option["label"].lower(),
        )

        user_ids = set(
            LogEntry.objects.filter(content_type__in=content_types)
            .order_by()
            .values_list("user_id", flat=True)
            .distinct()[:500]
        ) | set(
            SignInEvent.objects.exclude(user=None)
            .order_by()
            .values_list("user_id", flat=True)
            .distinct()[:500]
        )
        users = sorted(
            (
                {
                    "value": str(user.pk),
                    "label": str(user),
                    "username": user.get_username(),
                }
                for user in get_user_model()._default_manager.filter(pk__in=user_ids)
            ),
            key=lambda option: option["label"].lower(),
        )

        return {
            "models": models,
            "users": users,
            "actions": timeline.ACTIONS,
            "export_formats": get_export_formats(),
            "keep_days": cs_settings.AUDIT_LOG_KEEP_DAYS,
            "history": apps.is_installed("content_studio.history"),
        }

    @action(methods=["get"], detail=False, url_path=r"changes/(?P<entry_id>[0-9]+)")
    def change(self, request, entry_id):
        """
        The version the history app kept with an entry: the object's values
        after the change, the fields it changed and their values before.
        Answered for deleted objects too, read-only.
        """
        if not apps.is_installed("content_studio.history"):
            raise NotFound()

        from ...history.models import Version
        from ...snapshots import get_tracked_field_names

        entry = (
            LogEntry.objects.filter(
                pk=entry_id, content_type_id__in=viewable_content_type_ids(request)
            )
            .select_related("user", "content_type", "content_studio_action")
            .first()
        )

        if entry is None:
            raise NotFound()

        scoped = tenant_scoped_models([entry.content_type_id])

        if scoped and not visible_entries(request, [entry], scoped):
            raise NotFound()

        version = Version.objects.filter(log_entry=entry).first()
        model = entry.content_type.model_class()

        if version is None or model is None:
            raise NotFound()

        site = cs_settings.ADMIN_SITE
        studio = site._registry.get(model) if site.is_registered(model) else None
        tracked = get_tracked_field_names(model, studio)
        existing = existing_objects([entry])

        return Response(
            {
                **serialize_change(entry, existing, {entry.pk}),
                "fields": [name for name in version.fields if name in tracked],
                "previous": {
                    name: value
                    for name, value in version.previous.items()
                    if name in tracked
                },
                "data": {
                    name: value
                    for name, value in version.data.items()
                    if name in tracked
                },
            }
        )

    @action(methods=["get"], detail=False, url_path="export")
    def export(self, request):
        """The filtered timeline as a CSV or Excel file (?export_format=)."""
        export_format = request.query_params.get("export_format") or CSV

        if export_format not in get_export_formats():
            raise ValidationError(
                {
                    "export_format": [
                        f"Unknown or unavailable export format {export_format!r}."
                    ]
                }
            )

        filters = timeline.parse_filters(request.query_params)
        native = export_format == XLSX
        rows = self.iter_rows(request, filters, native=native)
        filename = f"audit-log-{timezone.localdate().isoformat()}.{export_format}"

        if export_format == XLSX:
            return rows_xlsx_response(rows, filename, _("Audit log"))

        return rows_csv_response(rows, filename)

    def iter_rows(self, request, filters, native=False):
        yield [
            _("Time"),
            _("User"),
            _("Action"),
            _("Model"),
            _("Object"),
            _("Object ID"),
            _("Message"),
            _("Username"),
            _("Method"),
            _("Reason"),
            _("IP address"),
            _("Browser"),
        ]

        cursor = None
        written = 0
        labels = action_labels()

        while written < EXPORT_MAX:
            items, cursor = timeline.get_page(request, filters, cursor, EXPORT_BATCH)

            for source, item in zip(items, serialize_page(items)):
                time = timezone.localtime(source.key.time)
                user = item["user"]
                is_change = item["kind"] == timeline.CHANGES
                yield [
                    time.replace(tzinfo=None) if native else time.isoformat(),
                    user["label"] if user else "",
                    labels.get(item["action"], item["action"]),
                    item["model_name"] if is_change else "",
                    item["object_repr"] if is_change else "",
                    item["object_id"] if is_change else "",
                    item["message"] if is_change else "",
                    "" if is_change else item["username"],
                    "" if is_change else item["method"],
                    "" if is_change else item["reason"],
                    "" if is_change else (item["ip_address"] or ""),
                    "" if is_change else item["browser"],
                ]
                written += 1

            if cursor is None:
                break


def action_labels() -> dict[str, str]:
    return {
        "created": _("Created"),
        "updated": _("Changed"),
        "deleted": _("Deleted"),
        "restored": _("Restored"),
        "reordered": _("Reordered"),
        "published": _("Published"),
        "unpublished": _("Unpublished"),
        SignInEvent.SIGNED_IN: _("Signed in"),
        SignInEvent.FAILED: _("Failed sign-in"),
        SignInEvent.SIGNED_OUT: _("Signed out"),
    }


def set_up_router():
    from ...router import content_studio_router

    content_studio_router.register(
        "api/audit-log", AuditLogViewSet, basename="content_studio_audit_log"
    )
