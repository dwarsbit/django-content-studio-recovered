"""
Bulk actions: batch operations the table view offers on selected rows.

A model studio declares custom actions with the @bulk_action decorator;
the built-in delete action is offered by default, the built-in export
when the studio offers export. The actions available to a request
(permissions included) serialize into the admin payload, and the bulk
endpoint dispatches to the decorated method with a tenant-scoped
queryset of the selected rows.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from django.core.exceptions import PermissionDenied
from django.db import router, transaction
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from .action_forms import ActionForm, get_action_form
from .signals import DELETED, record_change
from ._types import StrOrPromise

__all__ = [
    "bulk_action",
]

# The id of the built-in delete action.
DELETE_ACTION_ID = "delete"

# The id of the built-in export action.
EXPORT_ACTION_ID = "export"

# The id of the built-in duplicate row action.
DUPLICATE_ACTION_ID = "duplicate"

# The row actions a studio offers unless it lists its own.
DEFAULT_ROW_ACTIONS = (DUPLICATE_ACTION_ID, DELETE_ACTION_ID)

# The permission names an action may list in allowed_permissions,
# mirroring the classic admin.
BULK_ACTION_PERMISSIONS = ("add", "change", "delete", "view")


@dataclass(frozen=True)
class BulkActionMeta:
    """The metadata the @bulk_action decorator puts on a method."""

    label: Optional[StrOrPromise]
    icon: Optional[str]
    confirm: Optional[StrOrPromise]
    allowed_permissions: tuple[str, ...]
    destructive: bool
    # The inputs the action asks for before it runs: field names and
    # Field objects. Empty: it runs right away (after the confirm).
    fields: tuple = ()


def bulk_action(
    label=None,
    icon=None,
    confirm=None,
    allowed_permissions=None,
    destructive=False,
    fields=None,
):
    """
    Declare a bulk action on a ModelStudio method. The method receives
    the request and a queryset of the selected rows:

        @bulk_action(label="Publish", allowed_permissions=["change"])
        def publish(self, request, queryset):
            queryset.update(status=Article.Status.PUBLISHED)

    label defaults to the method name; icon is a Phosphor class (like
    the model icon); confirm, when set, is shown before the action runs;
    allowed_permissions gates the action on the model-level permissions
    it lists; by default the action needs change permission. An empty
    list opens it to anyone who can see the list. destructive marks
    actions that cannot be undone.

    fields makes the action ask for values in a dialog first: names of
    model fields, and Field(name, form_field=forms.CharField()) for
    inputs that are not on the model. The method then also receives
    the validated values:

        @bulk_action(label="Assign", fields=["author"])
        def assign(self, request, queryset, data):
            queryset.update(author=data["author"])
    """

    def decorator(func):
        func.bulk_action = BulkActionMeta(
            label=label,
            icon=icon,
            confirm=confirm,
            allowed_permissions=(
                ("change",)
                if allowed_permissions is None
                else tuple(allowed_permissions)
            ),
            destructive=destructive,
            fields=tuple(fields or ()),
        )
        return func

    # @bulk_action, without arguments: label carries the function.
    if callable(label):
        func, label = label, None
        return decorator(func)

    return decorator


@dataclass(frozen=True)
class BulkAction:
    """A resolved action: its id, handler and metadata. The handler
    receives the request and the selected queryset, and may return an
    int (a count) or a str (a message) for the response."""

    id: str
    handler: Callable
    meta: BulkActionMeta
    # The dialog's inputs, when the action declares fields.
    form: Optional[ActionForm] = None

    @property
    def label(self):
        if self.meta.label:
            return self.meta.label

        return capfirst(self.handler.__name__.replace("_", " "))

    # The formats the built-in export offers; None for other actions.
    formats: Optional[tuple[str, ...]] = None

    def serialize(self):
        data = {
            "id": self.id,
            "label": str(self.label),
            "icon": self.meta.icon,
            "confirm": str(self.meta.confirm) if self.meta.confirm else None,
            "destructive": self.meta.destructive,
        }

        # The export downloads a file instead of returning a result.
        if self.formats is not None:
            data["formats"] = list(self.formats)

        if self.form is not None:
            data["fields"] = self.form.serialize()

        return data

    def run(self, request, queryset, data=None):
        """Run the handler; an action with fields also gets the values."""
        if self.form is not None:
            return self.handler(request, queryset, data or {})

        return self.handler(request, queryset)


def _delete_action(studio):
    """
    The built-in delete: it records one change per object and deletes
    the selection through the studio's delete_queryset, which collects
    related rows and fires deletion signals like the classic admin.
    Returns the number of deleted objects.
    """

    def handler(request, queryset):
        objects = list(queryset)
        using = router.db_for_write(queryset.model)

        # Logged before deleting, which clears the objects' pks; the
        # transaction keeps the log and the deletion together.
        with transaction.atomic(using=using):
            for obj in objects:
                record_change(request, obj, DELETED)

            studio.delete_queryset(request, queryset)

        return len(objects)

    return handler


_DELETE_META = BulkActionMeta(
    label=_("Delete"),
    icon="ph-bold ph-trash",
    confirm=_("Are you sure you want to delete the selected items?"),
    allowed_permissions=("delete",),
    destructive=True,
)

_SOFT_DELETE_META = BulkActionMeta(
    label=_DELETE_META.label,
    icon=_DELETE_META.icon,
    confirm=_(
        "The selected items will be moved to the trash, where they can be "
        "restored. Are you sure you want to delete?"
    ),
    allowed_permissions=("delete",),
    destructive=False,
)


def _soft_delete_action(field):
    """
    The built-in delete for studios that configure soft_delete: it
    stamps the soft delete field instead of removing the rows, moving
    the selected objects to the trash, and records one change per
    object. Returns the number of trashed objects.
    """

    def handler(request, queryset):
        objects = list(queryset)
        queryset.update(**{field: timezone.now()})

        for obj in objects:
            record_change(request, obj, DELETED)

        return len(objects)

    return handler


_EXPORT_META = BulkActionMeta(
    label=_("Export"),
    icon="ph-bold ph-download-simple",
    confirm=None,
    allowed_permissions=("view",),
    destructive=False,
)


_ROW_DELETE_META = BulkActionMeta(
    label=_DELETE_META.label,
    icon=_DELETE_META.icon,
    confirm=_("Are you sure you want to delete this item?"),
    allowed_permissions=("delete",),
    destructive=True,
)

_ROW_SOFT_DELETE_META = BulkActionMeta(
    label=_DELETE_META.label,
    icon=_DELETE_META.icon,
    confirm=_(
        "The item will be moved to the trash, where it can be restored. "
        "Are you sure you want to delete it?"
    ),
    allowed_permissions=("delete",),
    destructive=False,
)

_DUPLICATE_META = BulkActionMeta(
    label=_("Duplicate"),
    icon="ph-bold ph-copy",
    confirm=None,
    allowed_permissions=("add",),
    destructive=False,
)


def _export_action(studio):
    """
    The built-in export: the selected rows as a download, in the format
    the request names under export_format (CSV by default).
    """
    from .export import export_response

    def handler(request, queryset):
        return export_response(
            studio, request, queryset, request.data.get("export_format")
        )

    return handler


def declared_bulk_actions(studio) -> dict[str, Callable]:
    """
    The @bulk_action methods of a studio, in definition order. Base
    classes come first; an override without the decorator replaces the
    inherited action.
    """
    actions = {}

    for klass in reversed(type(studio).__mro__):
        for name, attr in vars(klass).items():
            if callable(attr) and hasattr(attr, "bulk_action"):
                if name in actions:
                    del actions[name]
                actions[name] = getattr(studio, name)

    return actions


def get_bulk_actions(studio, request=None) -> list[BulkAction]:
    """
    The bulk actions offered to the request, in the configured order.

    The studio's actions attribute selects them: None (the default)
    offers the built-in delete, the built-in export (when the studio
    offers export) and every declared action, an empty list disables
    bulk actions entirely, and an explicit list offers exactly those
    names (with "delete" and "export" naming the built-ins). Actions the
    user lacks permission for are left out.
    """
    from .export import get_export_formats, is_exportable

    declared = declared_bulk_actions(studio)
    exportable = is_exportable(studio)

    names = getattr(studio, "actions", None)
    if names is None:
        names = [
            DELETE_ACTION_ID,
            *([EXPORT_ACTION_ID] if exportable else []),
            # A declared "export" gives way to the built-in, like the
            # system checks report.
            *(
                name
                for name in declared.keys()
                if not (exportable and name == EXPORT_ACTION_ID)
            ),
        ]

    actions = []

    for name in names:
        if name == EXPORT_ACTION_ID and exportable:
            action = BulkAction(
                id=name,
                handler=_export_action(studio),
                meta=_EXPORT_META,
                formats=tuple(get_export_formats()),
            )
        elif name == DELETE_ACTION_ID:
            action = _builtin_delete(studio)
        else:
            handler = declared.get(name)

            # Unresolvable names are reported by the system checks.
            if handler is None:
                continue

            action = _declared_action(studio, name, handler)

        if request is None or _allowed(studio, request, action.meta):
            actions.append(action)

    return actions


def _builtin_delete(studio) -> BulkAction:
    """The built-in delete. It honors a configured soft_delete: it moves
    the selection to the trash instead of removing it."""
    if getattr(studio, "soft_delete", ""):
        return BulkAction(
            id=DELETE_ACTION_ID,
            handler=_soft_delete_action(studio.soft_delete),
            meta=_SOFT_DELETE_META,
        )

    return BulkAction(
        id=DELETE_ACTION_ID, handler=_delete_action(studio), meta=_DELETE_META
    )


def get_row_actions(studio, request=None) -> list[BulkAction]:
    """
    The actions each row of the list offers in its menu, in the
    configured order: they run on that one object.

    The studio's row_actions attribute selects them by name, like
    actions does for the bulk bar: None (the default) offers the
    built-in duplicate and delete, an empty list none, and an explicit
    list exactly those names ("duplicate" and "delete" naming the
    built-ins, other names @bulk_action methods). Actions the user lacks
    permission for are left out. The duplicate has no handler: it opens
    the create form with a copy.
    """
    from .admin import is_duplicable

    declared = declared_bulk_actions(studio)
    names = getattr(studio, "row_actions", None)

    if names is None:
        names = DEFAULT_ROW_ACTIONS

    actions = []

    for name in names:
        if name == DUPLICATE_ACTION_ID:
            if not is_duplicable(studio):
                continue

            action = BulkAction(id=name, handler=None, meta=_DUPLICATE_META)
        elif name == DELETE_ACTION_ID:
            delete = _builtin_delete(studio)
            # Asked about the one row, not a selection.
            action = BulkAction(
                id=name,
                handler=delete.handler,
                meta=(
                    _ROW_SOFT_DELETE_META
                    if delete.meta is _SOFT_DELETE_META
                    else _ROW_DELETE_META
                ),
            )
        else:
            handler = declared.get(name)

            # Unresolvable names are reported by the system checks.
            if handler is None:
                continue

            action = _declared_action(studio, name, handler)

        if request is None or _allowed(studio, request, action.meta):
            actions.append(action)

    return actions


def _declared_action(studio, name, handler) -> BulkAction:
    meta = handler.bulk_action

    return BulkAction(
        id=name,
        handler=handler,
        meta=meta,
        form=get_action_form(studio.model, meta.fields),
    )


def _allowed(studio, request, meta: BulkActionMeta, obj=None) -> bool:
    """Whether the request may run an action: a gate on each of the
    permissions it lists, or none when it lists none. With an object,
    the gate applies to that object, and an action that lists none
    needs view permission on it."""
    if not meta.allowed_permissions:
        return obj is None or studio.has_view_permission(request, obj)

    return any(
        getattr(studio, f"has_{permission}_permission")(request, obj)
        for permission in meta.allowed_permissions
    )


def check_object_permissions(studio, request, meta: BulkActionMeta, queryset):
    """Raise PermissionDenied unless the request may run the action on
    every selected object, like the classic admin's delete_selected."""
    for obj in queryset:
        if not _allowed(studio, request, meta, obj):
            raise PermissionDenied(
                "You do not have permission to run this action on all "
                "selected objects."
            )
