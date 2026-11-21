"""
System checks for Content Studio configuration: the registry's model
studios, the extensions and the dashboard are validated whenever
Django's check framework runs (`manage.py check`, runserver startup,
`makemigrations` and CI).
"""

from importlib import import_module

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django import forms
from django.core import checks
from django.core.exceptions import FieldDoesNotExist
from django.db import models

from . import formats, widgets
from .actions import (
    BULK_ACTION_PERMISSIONS,
    DELETE_ACTION_ID,
    PUBLISHING_ACTION_IDS,
    DUPLICATE_ACTION_ID,
    EXPORT_ACTION_ID,
    declared_bulk_actions,
)
from .admin import (
    AdminSerializer,
    ContentStudioSite,
    declares,
    get_field_placements,
    get_is_singleton,
    get_write_only_field_names,
    get_table_display_columns,
    is_computed_column,
    iter_components,
    resolve_table_display,
)
from .export import is_exportable
from .extensions import DashboardPage
from .conditions import referenced_fields
from .form import (
    BaseText,
    Button,
    Component,
    Field,
    FieldLayout,
    FormSet,
    FormSetGroup,
    SEOPreview,
    TableColumn,
)
from .list_views import (
    VIEW_NAMES as LIST_VIEW_NAMES,
    CalendarView,
    calendar_field_error,
    get_calendars,
)
from .settings import cs_settings
from .throttling import parse_rate
from .translations import translated_attribute_names
from .utils import as_instance, flatten, get_tenant_field_name

LIST_COUNT_MODES = ("exact", "estimated", "none")


def config_name(owner) -> str:
    """
    The name to attribute configuration to: model studios arrive as
    instances, their inlines as classes.
    """
    if isinstance(owner, type):
        return owner.__name__

    return owner.__class__.__name__


def is_kind(value, base) -> bool:
    """
    Whether value is a widget or format of the given base type: a
    subclass, or an instance carrying options.
    """
    return isinstance(value, base) or (
        isinstance(value, type) and issubclass(value, base)
    )


# Widgets that render a field's choices; a field without any would
# leave them empty.
CHOICE_WIDGETS = (
    widgets.SelectWidget,
    widgets.MultiSelectWidget,
    widgets.ToggleGroupWidget,
    widgets.RadioButtonWidget,
)

# The media library's model contract, as documented: the fields the
# library's views rely on (tags stays optional).
MEDIA_MODEL_FIELDS = ("file", "name", "type")
MEDIA_FOLDER_MODEL_FIELDS = ("name", "parent")


def table_column_errors(studio) -> list[tuple[str, str]]:
    """
    Unresolvable or ambiguous table_display columns, as (check id,
    message) pairs. A column resolves to a model field, __str__ or a
    method on the studio; anything else would fail when rows are
    serialized. Column names must be unique and explicit formats must
    be format classes.
    """
    errors = []

    def validate(owner, model):
        if model is None:
            return

        model_field_names = (
            {field.name for field in model._meta.get_fields()}
            | model_property_names(model)
            | translated_attribute_names(model)
        )
        seen = set()

        for entry in resolve_table_display(owner):
            if isinstance(entry, str):
                column = TableColumn(field=entry)
            elif isinstance(entry, TableColumn):
                column = entry
            else:
                errors.append(
                    (
                        "content_studio.E006",
                        f"{config_name(owner)}.table_display entries must be "
                        f"field names or TableColumn objects; got {entry!r}.",
                    )
                )
                continue

            if column.field in seen:
                errors.append(
                    (
                        "content_studio.E006",
                        f"{config_name(owner)}.table_display contains a "
                        f"duplicate column {column.field!r}; column names must "
                        "be unique.",
                    )
                )
            seen.add(column.field)

            is_method = is_computed_column(owner, column)
            is_resolvable = (
                is_method
                or column.field == "__str__"
                or column.field in model_field_names
            )

            if not is_resolvable:
                errors.append(
                    (
                        "content_studio.E006",
                        f"{config_name(owner)}.table_display column "
                        f"{column.field!r} does not resolve to a model field, "
                        "a model property, __str__ or a method on the studio.",
                    )
                )

            if column.format is not None and not is_kind(
                column.format, formats.BaseFormat
            ):
                errors.append(
                    (
                        "content_studio.E006",
                        f"{config_name(owner)}.table_display column "
                        f"{column.field!r} has format {column.format!r}; formats "
                        "must be content_studio.formats classes or instances.",
                    )
                )

    model = getattr(studio, "model", None)
    validate(studio, model)

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline, getattr(inline, "model", None))

    return errors


def ignored_edit_field_names(model) -> set[str]:
    """
    Model field names the edit form never has to carry: the
    created/edited stamps from the settings, the tenant relation (set
    from the tenant header) and the user model's password, which the
    API leaves out entirely.
    """
    ignored = {
        name
        for name in (
            cs_settings.CREATED_BY_ATTR,
            cs_settings.EDITED_BY_ATTR,
            cs_settings.EDITED_AT_ATTR,
        )
        if hasattr(model, name)
    }

    try:
        tenant_field_name = get_tenant_field_name(model)
    except ValueError:
        tenant_field_name = None

    if tenant_field_name:
        ignored.add(tenant_field_name)

    if model is get_user_model():
        ignored.add("password")

        if get_user_model().USERNAME_FIELD != "username":
            ignored.add("username")

    return ignored


def is_required_model_field(field) -> bool:
    """
    Whether the API would reject a save without the field, mirroring
    the serializer: editable, not nullable, not blank and without a
    default.
    """
    return (
        field.editable
        and not field.auto_created
        and not field.blank
        and not field.null
        and not field.has_default()
    )


def edit_field_warnings(studio) -> list[tuple[str, str]]:
    """
    Required model fields missing from the edit form, as (check id,
    message) pairs.

    An unset edit_main falls back to every editable field, so only
    explicit configurations are at risk; required fields dropped
    through exclude are reported all the same.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    form_fields = edit_form_field_names(studio)
    ignored = ignored_edit_field_names(model)

    warnings = []

    for field in model._meta.get_fields():
        if (
            not is_required_model_field(field)
            or field.name in ignored
            or field.name in form_fields
        ):
            continue

        warnings.append(
            (
                "content_studio.W001",
                f"{studio.__class__.__name__}: the required field "
                f"{field.name!r} is not in edit_main or edit_sidebar, so "
                "saving objects will fail validation. Add the field to the "
                "edit form or give the model field a default, make it "
                "nullable or blank, or exclude it consciously by filling it "
                "in programmatically.",
            )
        )

    return warnings


def edit_form_field_names(studio) -> set[str]:
    """
    The model field names the edit form exposes, mirroring
    AdminSerializer's normalization of edit_main and edit_sidebar. An
    unset edit_main falls back to every editable field minus exclude.
    """
    serializer = AdminSerializer(studio)
    names = set()

    edit_main = getattr(studio, "edit_main", None) or []

    if not edit_main:
        names.update(studio.get_fields(None))
    else:
        for group in serializer.get_edit_main(edit_main):
            names.update(_field_names(group.get_fields()))

    for form_set in serializer.get_edit_sidebar(getattr(studio, "edit_sidebar", None)):
        names.update(_field_names(form_set.get_fields()))

    return names


def _field_names(fields) -> set[str]:
    """The names of Field entries; Components are custom UI and carry no
    model field name."""
    return {field.name for field in fields if isinstance(field, Field)}


def bulk_action_errors(studio) -> list[tuple[str, str]]:
    """
    Misconfigured bulk actions, as (check id, message) pairs. An
    explicit actions list must name the built-in delete or a declared
    @bulk_action method (and each name only once); declared actions may
    not shadow the built-in delete or list unknown permissions.
    """
    errors = []
    declared = declared_bulk_actions(studio)
    actions = getattr(studio, "actions", None)

    if name := next((name for name in declared if name == DELETE_ACTION_ID), None):
        errors.append(
            (
                "content_studio.E007",
                f"{studio.__class__.__name__}.bulk action {name!r} shadows "
                "the built-in delete action; give it another name.",
            )
        )

    exportable = is_exportable(studio)

    if exportable and EXPORT_ACTION_ID in declared:
        errors.append(
            (
                "content_studio.E007",
                f"{studio.__class__.__name__}.bulk action "
                f"{EXPORT_ACTION_ID!r} shadows the built-in export action; "
                "give it another name.",
            )
        )

    if actions is not None:
        seen = set()

        for name in actions:
            if name == EXPORT_ACTION_ID and not exportable and name not in declared:
                errors.append(
                    (
                        "content_studio.E007",
                        f"{studio.__class__.__name__}.actions contains "
                        f"{name!r}, but the studio offers no export; set "
                        "export_fields or allow_export.",
                    )
                )
            elif name in PUBLISHING_ACTION_IDS and name not in declared:
                from .publishing import get_publishing

                if get_publishing(studio) is None:
                    errors.append(
                        (
                            "content_studio.E007",
                            f"{studio.__class__.__name__}.actions contains "
                            f"{name!r}, but the studio has no publishing; set "
                            "publishing.",
                        )
                    )
            elif (
                name not in (DELETE_ACTION_ID, EXPORT_ACTION_ID)
                and name not in declared
            ):
                errors.append(
                    (
                        "content_studio.E007",
                        f"{studio.__class__.__name__}.actions contains "
                        f"{name!r}, which is not a @bulk_action method "
                        "(or the built-in delete or export).",
                    )
                )

            if name in seen:
                errors.append(
                    (
                        "content_studio.E007",
                        f"{studio.__class__.__name__}.actions contains "
                        f"{name!r} more than once.",
                    )
                )
            seen.add(name)

    for name, handler in declared.items():
        unknown = [
            permission
            for permission in handler.bulk_action.allowed_permissions
            if permission not in BULK_ACTION_PERMISSIONS
        ]

        if unknown:
            errors.append(
                (
                    "content_studio.E007",
                    f"{studio.__class__.__name__}.bulk action {name!r} lists "
                    f"unknown permission(s) {', '.join(unknown)}. Available: "
                    f"{', '.join(BULK_ACTION_PERMISSIONS)}.",
                )
            )

    errors.extend(_action_list_errors(studio, declared))

    return errors


def _action_list_errors(studio, declared) -> list[tuple[str, str]]:
    """
    An explicit row_actions list must name the built-in duplicate or
    delete, or a declared @bulk_action method; edit_actions only
    declared methods (the edit page has its own duplicate and delete).
    Each name only once; a declared action may not shadow the built-in
    duplicate.
    """
    errors = []
    name = studio.__class__.__name__

    if DUPLICATE_ACTION_ID in declared:
        errors.append(
            (
                "content_studio.E007",
                f"{name}.bulk action {DUPLICATE_ACTION_ID!r} shadows the "
                "built-in duplicate row action; give it another name.",
            )
        )

    # Studios with publishing offer its actions in the rows too.
    publishing = PUBLISHING_ACTION_IDS if getattr(studio, "publishing", None) else ()

    for attribute, builtins in (
        ("row_actions", (DELETE_ACTION_ID, DUPLICATE_ACTION_ID, *publishing)),
        ("edit_actions", ()),
    ):
        names = getattr(studio, attribute, None)

        if names is None:
            continue

        seen = set()

        for action in names:
            if action not in builtins and action not in declared:
                errors.append(
                    (
                        "content_studio.E007",
                        f"{name}.{attribute} contains {action!r}, which is not "
                        "a @bulk_action method"
                        + (
                            " (or the built-in duplicate or delete)."
                            if builtins
                            else "."
                        ),
                    )
                )

            if action in seen:
                errors.append(
                    (
                        "content_studio.E007",
                        f"{name}.{attribute} contains {action!r} more than once.",
                    )
                )
            seen.add(action)

    return errors


def action_form_errors(studio) -> list[tuple[str, str]]:
    """
    Misconfigured action dialogs, as (check id, message) pairs: the
    fields of @bulk_action methods and of Buttons on the edit page.
    """
    from .action_forms import get_form_field_type
    from .conditions import iter_conditions

    model = getattr(studio, "model", None)

    if model is None:
        return []

    owners = [
        (f"bulk action {name!r}", handler.bulk_action.fields, handler)
        for name, handler in declared_bulk_actions(studio).items()
    ] + [
        (f"Button {component.label!r}", component.fields, component.handle)
        for component in iter_components(studio)
        if isinstance(component, Button)
    ]

    errors = []
    excluded = set(getattr(studio, "exclude", None) or [])

    def error(owner, message):
        errors.append(
            ("content_studio.E051", f"{config_name(studio)}: {owner} {message}")
        )

    for owner, fields, handler in owners:
        if not fields:
            continue

        entries = []

        for entry in fields:
            if isinstance(entry, str):
                entry = Field(entry)

            if not isinstance(entry, Field):
                error(owner, f"has {entry!r} in fields: use names or Field objects.")
                continue

            entries.append(entry)

            if entry.form_field is not None:
                if not isinstance(entry.form_field, forms.Field):
                    error(
                        owner,
                        f"gives Field({entry.name!r}) a form_field that is not "
                        "a Django form field.",
                    )
                elif get_form_field_type(entry.form_field) is None:
                    error(
                        owner,
                        f"gives Field({entry.name!r}) a "
                        f"{entry.form_field.__class__.__name__}, which the "
                        "dialog cannot show.",
                    )
                continue

            try:
                model_field = model._meta.get_field(entry.name)
            except FieldDoesNotExist:
                model_field = None

            if model_field is None or not getattr(model_field, "concrete", False):
                error(
                    owner,
                    f"has {entry.name!r} in fields, which is not a field of "
                    f"{model._meta.label_lower}; give it a form_field.",
                )
            elif (
                not model_field.editable
                or model_field.primary_key
                or entry.name in excluded
            ):
                error(
                    owner,
                    f"has {entry.name!r} in fields, which is not editable or "
                    "is excluded, so the dialog cannot set it.",
                )

        names = [entry.name for entry in entries]

        if len(set(names)) != len(names):
            error(owner, "lists a field more than once.")

        for entry in entries:
            if entry.when is None:
                continue

            if any(iter_conditions(entry.when)):
                error(
                    owner,
                    f"uses a Condition in the when= of Field({entry.name!r}); "
                    "action dialogs take Q objects only.",
                )

            for name in referenced_fields(entry.when):
                if name not in names:
                    error(
                        owner,
                        f"has a condition on Field({entry.name!r}) that reads "
                        f"{name!r}, which is not one of its fields.",
                    )

        if not _takes_data(handler):
            error(
                owner,
                "has fields, so its handler receives their values as an extra "
                "argument (data); add it.",
            )

    return errors


def _takes_data(handler) -> bool:
    """Whether a bound handler takes three arguments: (request,
    queryset, data) or (obj, request, data)."""
    import inspect

    try:
        parameters = list(inspect.signature(handler).parameters.values())
    except (TypeError, ValueError):
        return True

    if any(p.kind == p.VAR_POSITIONAL for p in parameters):
        return True

    positional = [
        p for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]

    return len(positional) >= 3


def calendar_errors(studio) -> list[tuple[str, str]]:
    """
    Calendars that cannot be drawn, as (check id, message) pairs: a
    bare "calendar" without publishing (E059), and a calendar whose
    date or end field is not a date field, or whose date another
    calendar already shows (E060).
    """
    errors = []
    name = studio.__class__.__name__
    keys = set()

    for view in get_calendars(studio):
        field = view.resolve_field(studio)

        if field is None:
            errors.append(
                (
                    "content_studio.E059",
                    f'{name}.list_views offers "calendar", which shows the '
                    "publishing date, but the studio has no publishing. "
                    'Name the date field instead: CalendarView("<field>").',
                )
            )
            continue

        for role, field_name in (("field", field), ("end", view.end)):
            if role == "end" and not field_name:
                continue

            reason = calendar_field_error(studio, field_name)

            if reason:
                errors.append(
                    (
                        "content_studio.E060",
                        f"{name}.list_views has a calendar whose {role} " f"{reason}.",
                    )
                )

        key = view.key(studio)

        if key in keys:
            errors.append(
                (
                    "content_studio.E060",
                    f"{name}.list_views has two calendars of '{field}'.",
                )
            )

        keys.add(key)

    return errors


def list_config_errors(studio) -> list[tuple[str, str]]:
    """
    Misconfigured list pages, as (check id, message) pairs. list_display
    is the Django admin's name for the table columns; a mapping there is
    the list view's role mapping, which lives in list_item_display, and
    must not be silently ignored.
    """
    errors = []

    if isinstance(studio.list_display, dict):
        errors.append(
            (
                "content_studio.E001",
                f"{studio.__class__.__name__}.list_display is a mapping. "
                "The list view's role mapping is configured with "
                "list_item_display; list_display, like table_display, "
                "configures the table columns.",
            )
        )

    name = studio.__class__.__name__
    unknown_views = [
        repr(view)
        for view in studio.list_views
        if not isinstance(view, CalendarView)
        and not (isinstance(view, str) and view in LIST_VIEW_NAMES)
    ]

    if unknown_views:
        errors.append(
            (
                "content_studio.E002",
                f"{name}.list_views contains unknown "
                f"view(s) {', '.join(unknown_views)}. Available views: "
                f"{', '.join(sorted(LIST_VIEW_NAMES))} and CalendarView "
                "objects (content_studio.list_views).",
            )
        )
    else:
        errors.extend(calendar_errors(studio))

    list_count = getattr(studio, "list_count", "exact")

    if list_count not in LIST_COUNT_MODES:
        errors.append(
            (
                "content_studio.E046",
                f"{studio.__class__.__name__}.list_count is {list_count!r}. "
                f"Available: {', '.join(LIST_COUNT_MODES)}.",
            )
        )

    return errors


def duplicate_id_errors(site) -> list[tuple[str, str]]:
    """
    Extension, dashboard widget and component ID collisions, as (check
    id, message) pairs. IDs are derived from the class and its
    label/url/name by default, so duplicates mean an explicit ID is
    needed.
    """
    errors = []

    seen = {}
    for extension in getattr(site, "extensions", None) or []:
        key = str(extension.extension_id)
        if key in seen:
            errors.append(
                (
                    "content_studio.E003",
                    f"Duplicate extension ID {key}: "
                    f"{seen[key]} and {extension.__class__.__name__}. "
                    "Pass extension_id to disambiguate.",
                )
            )
        seen[key] = extension.__class__.__name__

    # One endpoint serves the widgets of every dashboard, so their IDs
    # must be unique across the site dashboard and the dashboard pages.
    seen = {}
    for widget in iter_dashboard_widgets(site):
        key = str(widget.widget_id)
        if key in seen:
            errors.append(
                (
                    "content_studio.E004",
                    f"Duplicate dashboard widget ID {key}: "
                    f"{seen[key]} and {widget.__class__.__name__}. "
                    "Pass widget_id to disambiguate.",
                )
            )
        seen[key] = widget.__class__.__name__

    # Components are looked up per studio: a model studio serves its
    # own, an inline serves its own and falls back on the studio of the
    # inlined model. IDs must be unique within each of those scopes;
    # the same component class may serve several studios.
    for model, studio in site._registry.items():
        scopes = [(studio.__class__.__name__, list(iter_components(studio)))]

        for inline in studio.inlines:
            components = list(iter_components(inline))
            inline_model_studio = site._registry.get(getattr(inline, "model", None))

            if inline_model_studio is not None:
                components.extend(iter_components(inline_model_studio))

            scopes.append((inline.__name__, components))

        for scope, components in scopes:
            seen = {}

            for component in components:
                key = str(component.component_id)
                if key in seen:
                    errors.append(
                        (
                            "content_studio.E005",
                            f"Duplicate component ID {key}: "
                            f"{seen[key]} and {component.__class__.__name__} "
                            f"in {scope}. "
                            "Pass component_id to disambiguate.",
                        )
                    )
                seen[key] = component.__class__.__name__

    return errors


def soft_delete_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured soft_delete, as (check id, message) pairs. The
    configured field must exist and be a nullable date or datetime
    field: the trash stamps it and the lists filter on it being empty.
    """
    errors = []

    if not studio.soft_delete:
        return errors

    try:
        field = studio.model._meta.get_field(studio.soft_delete)
    except FieldDoesNotExist:
        errors.append(
            (
                "content_studio.E008",
                f"{studio.__class__.__name__}.soft_delete refers to the "
                f"unknown field '{studio.soft_delete}'.",
            )
        )
        return errors

    if not isinstance(field, models.DateField) or not field.null:
        errors.append(
            (
                "content_studio.E008",
                f"{studio.__class__.__name__}.soft_delete must name a "
                "nullable date or datetime field; "
                f"'{studio.soft_delete}' is not.",
            )
        )

    return errors


def publishing_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured publishing, as (check id, message) pairs: a field
    name or a Publishing, whose date fields are nullable DateTimeFields
    of the model and whose status field takes the values given for the
    states.
    """
    from .publishing import STATES, Publishing, check_field, get_publishing

    value = getattr(studio, "publishing", None)
    name = studio.__class__.__name__

    if value in (None, ""):
        return []

    if not isinstance(value, (str, Publishing)):
        return [
            (
                "content_studio.E054",
                f"{name}.publishing must be the name of a date field or a "
                f"Publishing; got {value!r}.",
            )
        ]

    config = get_publishing(studio)
    model = studio.model
    errors = []

    if get_is_singleton(studio):
        errors.append(
            (
                "content_studio.E054",
                f"{name}.publishing is not supported on a singleton.",
            )
        )

    for attribute in ("published_at", "unpublish_at"):
        field_name = getattr(config, attribute)

        if not field_name:
            continue

        problem = check_field(model, field_name)

        if problem:
            errors.append(
                (
                    "content_studio.E054",
                    f"{name}.publishing {attribute}: {problem}.",
                )
            )

    if config.unpublish_at and config.unpublish_at == config.published_at:
        errors.append(
            (
                "content_studio.E054",
                f"{name}.publishing unpublish_at must differ from published_at.",
            )
        )

    if config.pending_changes and not apps.is_installed("content_studio.history"):
        errors.append(
            (
                "content_studio.E054",
                f"{name}.publishing has pending_changes, which needs "
                f"'content_studio.history' in INSTALLED_APPS.",
            )
        )

    if config.status_values and not config.status:
        errors.append(
            (
                "content_studio.E054",
                f"{name}.publishing has status_values but no status field.",
            )
        )

    if config.status:
        try:
            field = model._meta.get_field(config.status)
        except FieldDoesNotExist:
            errors.append(
                (
                    "content_studio.E054",
                    f"{name}.publishing status: '{config.status}' is not a "
                    f"field of {model._meta.label}.",
                )
            )
            return errors

        unknown = [key for key in config.status_values if key not in STATES]

        if unknown:
            errors.append(
                (
                    "content_studio.E054",
                    f"{name}.publishing status_values has unknown state(s) "
                    f"{', '.join(map(repr, unknown))}; the states are "
                    f"{', '.join(STATES)}.",
                )
            )

        missing = [
            key for key in ("draft", "published") if key not in config.status_values
        ]

        if missing:
            errors.append(
                (
                    "content_studio.E054",
                    f"{name}.publishing status_values needs a value for "
                    f"{' and '.join(missing)}.",
                )
            )

        choices = {
            str(choice)
            for choice, _label in (getattr(field, "flatchoices", None) or [])
        }

        if choices:
            bad = [
                value
                for value in config.status_values.values()
                if str(value) not in choices
            ]

            if bad:
                errors.append(
                    (
                        "content_studio.E054",
                        f"{name}.publishing status_values: "
                        f"{', '.join(map(repr, bad))} not among the choices "
                        f"of '{config.status}'.",
                    )
                )

    return errors


def review_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured review (E058): True or a Review, on a studio with
    publishing, with the review app installed.
    """
    from django.apps import apps as django_apps

    from .publishing import get_publishing
    from .review import Review

    value = getattr(studio, "review", None)
    name = studio.__class__.__name__

    if value in (None, False):
        return []

    if value is not True and not isinstance(value, Review):
        return [
            (
                "content_studio.E058",
                f"{name}.review must be True or a Review; got {value!r}.",
            )
        ]

    errors = []

    if get_publishing(studio) is None:
        errors.append(
            (
                "content_studio.E058",
                f"{name}.review needs publishing: set {name}.publishing.",
            )
        )

    if not django_apps.is_installed("content_studio.review"):
        errors.append(
            (
                "content_studio.E058",
                f"{name}.review needs the review app: add "
                f"'content_studio.review' to INSTALLED_APPS.",
            )
        )

    return errors


def reorder_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured reorder_field or reorder_scope, as (check id,
    message) pairs. The field must exist and, unless the studio
    overrides reorder, be numeric: the built-in implementation rewrites
    it. Scope entries must be concrete fields. Inlines are checked too.
    """
    from .admin import BaseStudio
    from .reordering import NUMERIC_FIELDS

    errors = []

    def error(owner, message):
        errors.append(("content_studio.E017", f"{config_name(owner)}.{message}"))

    def validate(owner, model):
        field_name = getattr(owner, "reorder_field", None)

        if model is None or not field_name:
            return

        try:
            field = model._meta.get_field(field_name)
        except (FieldDoesNotExist, TypeError):
            error(
                owner,
                f"reorder_field refers to {field_name!r}, which is not a "
                f"field of {model._meta.label_lower}.",
            )
            return

        cls = owner if isinstance(owner, type) else type(owner)
        overridden = getattr(cls, "reorder", None) is not BaseStudio.reorder

        if not overridden and not isinstance(field, NUMERIC_FIELDS):
            error(
                owner,
                f"reorder_field must name a numeric field; {field_name!r} is "
                "not. Override reorder() for another ordering implementation.",
            )

        for name in getattr(owner, "reorder_scope", None) or []:
            try:
                scope_field = model._meta.get_field(name)
            except (FieldDoesNotExist, TypeError):
                scope_field = None

            if scope_field is None or not getattr(scope_field, "concrete", False):
                error(
                    owner,
                    f"reorder_scope contains {name!r}, which is not a field "
                    f"of {model._meta.label_lower}.",
                )

    validate(studio, getattr(studio, "model", None))

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline, getattr(inline, "model", None))

    return errors


def media_upload_errors() -> list[tuple[str, str]]:
    """
    Malformed upload settings, as (check id, message) pairs: the allowed
    extensions (media library and FileWidget) must be a list of strings without a
    leading dot, the maximum size a positive number of bytes.
    """
    errors = []
    max_size = cs_settings.MEDIA_LIBRARY_MAX_UPLOAD_SIZE

    for setting in ("MEDIA_LIBRARY_ALLOWED_EXTENSIONS", "UPLOAD_ALLOWED_EXTENSIONS"):
        extensions = getattr(cs_settings, setting)

        if extensions is not None and (
            isinstance(extensions, str)
            or not isinstance(extensions, (list, tuple, set))
            or not all(
                isinstance(e, str) and e and not e.startswith(".") for e in extensions
            )
        ):
            errors.append(
                (
                    "content_studio.E014",
                    f"{setting} must be None or a list of file extensions "
                    "without the leading dot, like ['jpg', 'pdf'].",
                )
            )

    if max_size is not None and (
        isinstance(max_size, bool) or not isinstance(max_size, int) or max_size <= 0
    ):
        errors.append(
            (
                "content_studio.E014",
                "MEDIA_LIBRARY_MAX_UPLOAD_SIZE must be None or a positive "
                "number of bytes.",
            )
        )

    from django.core.files.storage import InvalidStorageError, storages

    try:
        storages[cs_settings.UPLOAD_STORAGE]
    except (InvalidStorageError, TypeError):
        errors.append(
            (
                "content_studio.E014",
                f"UPLOAD_STORAGE {cs_settings.UPLOAD_STORAGE!r} is not in STORAGES.",
            )
        )

    return errors


def _is_positive_number(value, integer=False) -> bool:
    types = int if integer else (int, float)
    return not isinstance(value, bool) and isinstance(value, types) and value > 0


def webhook_setting_errors() -> list[tuple[str, str]]:
    """
    Malformed webhook settings, as (check id, message) pairs: the
    allowed hosts must be a list of host names, the attempts and the
    retention positive whole numbers, the timeout a positive number.
    """
    errors = []
    hosts = cs_settings.WEBHOOK_ALLOWED_HOSTS

    if (
        isinstance(hosts, str)
        or not isinstance(hosts, (list, tuple, set))
        or not all(isinstance(host, str) and host for host in hosts)
    ):
        errors.append(
            (
                "content_studio.E019",
                "WEBHOOK_ALLOWED_HOSTS must be a list of host names, like "
                "['build.internal'].",
            )
        )

    if not _is_positive_number(cs_settings.WEBHOOK_MAX_ATTEMPTS, integer=True):
        errors.append(
            (
                "content_studio.E019",
                "WEBHOOK_MAX_ATTEMPTS must be a positive whole number.",
            )
        )

    if not _is_positive_number(cs_settings.WEBHOOK_TIMEOUT):
        errors.append(
            (
                "content_studio.E019",
                "WEBHOOK_TIMEOUT must be a positive number of seconds.",
            )
        )

    retention = cs_settings.WEBHOOK_DELIVERY_RETENTION

    if retention is not None and not _is_positive_number(retention, integer=True):
        errors.append(
            (
                "content_studio.E019",
                "WEBHOOK_DELIVERY_RETENTION must be None or a positive whole "
                "number of days.",
            )
        )

    return errors


def _is_absolute_url(value) -> bool:
    from urllib.parse import urlsplit

    if not isinstance(value, str):
        return False

    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def notification_errors() -> list[tuple[str, str]]:
    """
    A malformed NOTIFICATION_RETENTION or NOTIFICATION_UNREAD_RETENTION
    (E030), notification events registered with a malformed key or twice
    with different definitions (E031), and a malformed
    NOTIFICATION_EMAIL_DIGEST or ADMIN_URL (E032), as (check id, message)
    pairs.
    """
    errors = []

    for setting in ("NOTIFICATION_RETENTION", "NOTIFICATION_UNREAD_RETENTION"):
        retention = getattr(cs_settings, setting)

        if retention is not None and not _is_positive_number(retention, integer=True):
            errors.append(
                (
                    "content_studio.E030",
                    f"{setting} must be None or a positive whole number of days.",
                )
            )

    digest = cs_settings.NOTIFICATION_EMAIL_DIGEST
    admin_url = cs_settings.ADMIN_URL

    if not isinstance(digest, bool):
        errors.append(
            ("content_studio.E032", "NOTIFICATION_EMAIL_DIGEST must be True or False.")
        )

    if admin_url is not None and not _is_absolute_url(admin_url):
        errors.append(
            (
                "content_studio.E032",
                "ADMIN_URL must be None or the admin's absolute URL, like "
                '"https://example.com/admin/".',
            )
        )
    elif digest is True and admin_url is None:
        errors.append(
            (
                "content_studio.E032",
                "NOTIFICATION_EMAIL_DIGEST needs ADMIN_URL, the admin's absolute "
                "URL, for the links in the emails.",
            )
        )

    from django.apps import apps

    if apps.is_installed("content_studio.notifications"):
        from .notifications.events import registration_errors

        errors += [("content_studio.E031", error) for error in registration_errors()]

    return errors


def status_errors() -> list[tuple[str, str]]:
    """
    Services and recurring tasks registered for the status page with a
    malformed key, without a check or twice with different definitions
    (E047), as (check id, message) pairs.
    """
    from django.apps import apps

    if not apps.is_installed("content_studio.contrib.status"):
        return []

    from .contrib.status.registry import registration_errors

    return [("content_studio.E047", error) for error in registration_errors()]


def backup_errors() -> list[tuple[str, str]]:
    """
    Backup settings that cannot work (E050): BACKUP_STORAGE not in
    STORAGES, an unknown alias in BACKUP_DATABASES, a BACKUP_SCHEDULE
    that is not a cron expression, BACKUP_KEEP below 1, an unknown app
    or model in BACKUP_EXCLUDE, or a BACKUP_UPLOAD_MAX_SIZE below 1.
    """
    from django.apps import apps
    from django.conf import settings
    from django.core.files.storage import InvalidStorageError, storages

    if not apps.is_installed("content_studio.contrib.backups"):
        return []

    from .contrib.backups.schedule import ScheduleError, parse

    errors = []

    try:
        storages[cs_settings.BACKUP_STORAGE]
    except InvalidStorageError:
        errors.append(
            f"BACKUP_STORAGE {cs_settings.BACKUP_STORAGE!r} is not in STORAGES."
        )

    databases = cs_settings.BACKUP_DATABASES

    if not isinstance(databases, (list, tuple)):
        errors.append("BACKUP_DATABASES must be a list of database aliases.")
    else:
        for alias in databases:
            if alias not in settings.DATABASES:
                errors.append(f"BACKUP_DATABASES names {alias!r}, not in DATABASES.")

    if cs_settings.BACKUP_SCHEDULE:
        try:
            parse(cs_settings.BACKUP_SCHEDULE)
        except ScheduleError as exc:
            errors.append(f"BACKUP_SCHEDULE {cs_settings.BACKUP_SCHEDULE!r}: {exc}")

    keep = cs_settings.BACKUP_KEEP

    if keep is not None and (not isinstance(keep, int) or keep < 1):
        errors.append("BACKUP_KEEP must be a whole number of 1 or more, or None.")

    for label in cs_settings.BACKUP_EXCLUDE or []:
        app_label, _dot, model_name = str(label).partition(".")

        try:
            config = apps.get_app_config(app_label)
            if model_name:
                config.get_model(model_name)
        except LookupError:
            errors.append(f"BACKUP_EXCLUDE names {label!r}, no installed app or model.")

    max_size = cs_settings.BACKUP_UPLOAD_MAX_SIZE

    if max_size is not None and (
        not isinstance(max_size, int) or isinstance(max_size, bool) or max_size < 1
    ):
        errors.append(
            "BACKUP_UPLOAD_MAX_SIZE must be a number of bytes of 1 or more, or None."
        )

    return [("content_studio.E050", error) for error in errors]


def is_inside_media_root(location) -> bool:
    from pathlib import Path

    if not settings.MEDIA_ROOT:
        return False

    media_root = Path(settings.MEDIA_ROOT).resolve()
    path = Path(location).resolve()
    return path == media_root or media_root in path.parents


def is_public_storage(storage) -> bool:
    """
    Whether a storage may serve its files to anyone: a FileSystemStorage
    inside MEDIA_ROOT (web servers serve it), or an object storage with a
    public ACL or unsigned URLs.
    """
    from django.core.files.storage import FileSystemStorage

    if isinstance(storage, FileSystemStorage):
        return is_inside_media_root(storage.location)

    return (
        getattr(storage, "default_acl", None) in ("public-read", "public-read-write")
        or getattr(storage, "querystring_auth", True) is False
    )


def backup_storage_errors() -> list[tuple[str, str]]:
    """
    Backups saved in a storage that may serve them publicly (E052). A
    project whose web server refuses the backup folder silences it.
    """
    from django.apps import apps
    from django.core.files.storage import InvalidStorageError, storages

    if not apps.is_installed("content_studio.contrib.backups"):
        return []

    try:
        storage = storages[cs_settings.BACKUP_STORAGE]
    except InvalidStorageError:
        # E050 reports it.
        return []

    if not is_public_storage(storage):
        return []

    return [
        (
            "content_studio.E052",
            f"Backups are saved in the {cs_settings.BACKUP_STORAGE!r} storage, "
            f"which may serve {cs_settings.BACKUP_FOLDER!r} publicly. A backup "
            "holds the whole database, password hashes and two-factor secrets "
            "included. Set BACKUP_STORAGE to a private storage in STORAGES, "
            "outside MEDIA_ROOT. If your web server refuses the folder, add "
            "content_studio.E052 to SILENCED_SYSTEM_CHECKS.",
        )
    ]


def backup_warnings() -> list[tuple[str, str]]:
    """
    A BACKUP_SCHEDULE without Huey to run it (W028): run
    content_studio_backup from cron, and silence the warning.
    """
    from django.apps import apps

    if not apps.is_installed("content_studio.contrib.backups"):
        return []

    warnings = []

    if cs_settings.BACKUP_SCHEDULE and not apps.is_installed("huey.contrib.djhuey"):
        warnings.append(
            (
                "content_studio.W028",
                f"BACKUP_SCHEDULE is {cs_settings.BACKUP_SCHEDULE!r} but Huey is "
                "not installed to run it. Run `manage.py content_studio_backup` "
                "from cron on that schedule, then add content_studio.W028 to "
                "SILENCED_SYSTEM_CHECKS.",
            )
        )

    return warnings


def media_json_attr_errors(
    setting, check_id, purpose, explicit_only=False
) -> list[tuple[str, str]]:
    """
    A misconfigured setting naming a JSONField on the media item model
    (MEDIA_METADATA_ATTR, MEDIA_PROPERTIES_ATTR), as (check id, message)
    pairs. The attribute must exist on the media item model and be a
    JSONField. With explicit_only, a default value is not checked.
    """
    errors = []

    attr = getattr(cs_settings, setting)

    if not attr or (explicit_only and setting not in cs_settings.user_settings):
        return errors

    media_model = cs_settings.MEDIA_LIBRARY_MODEL

    if not media_model:
        errors.append(
            (
                check_id,
                f"{setting} is set but MEDIA_LIBRARY_MODEL is not; "
                f"the {purpose} attribute needs a media item model.",
            )
        )
        return errors

    try:
        field = media_model._meta.get_field(attr)
    except FieldDoesNotExist:
        errors.append(
            (
                check_id,
                f"{setting} refers to the unknown field '{attr}' on "
                f"{media_model._meta.label_lower}.",
            )
        )
        return errors

    if not isinstance(field, models.JSONField):
        errors.append(
            (
                check_id,
                f"{setting} must name a JSONField; '{attr}' on "
                f"{media_model._meta.label_lower} is not.",
            )
        )

    return errors


def focal_point_errors() -> list[tuple[str, str]]:
    """
    FOCAL_POINT_ATTR still set, as (check id, message) pairs. The
    setting is removed: the focal point is a media item property
    (properties["focal_point"]), so a site's own field is no longer
    read.
    """
    if "FOCAL_POINT_ATTR" not in cs_settings.user_settings:
        return []

    return [
        (
            "content_studio.E009",
            "FOCAL_POINT_ATTR is removed: the focal point is stored in the "
            "media item's properties (MEDIA_PROPERTIES_ATTR), as "
            'properties["focal_point"]. Move existing focal points there '
            "and remove the setting.",
        )
    ]


def media_properties_errors() -> list[tuple[str, str]]:
    """
    A misconfigured MEDIA_PROPERTIES_ATTR, as (check id, message) pairs.
    Only a value set explicitly is checked, as for MEDIA_METADATA_ATTR.
    """
    return media_json_attr_errors(
        "MEDIA_PROPERTIES_ATTR",
        "content_studio.E026",
        "properties",
        explicit_only=True,
    )


def media_metadata_errors() -> list[tuple[str, str]]:
    """
    A misconfigured MEDIA_METADATA_ATTR, as (check id, message) pairs.
    Uploads store the metadata read from the file in it. Only a value
    set explicitly is checked: the default ("metadata") applies to every
    media model, and one without that field has no metadata.
    """
    return media_json_attr_errors(
        "MEDIA_METADATA_ATTR", "content_studio.E025", "metadata", explicit_only=True
    )


def model_field_names(model) -> set[str]:
    """
    The model's own field names, mirroring what the frontend receives:
    concrete fields and many-to-many relations.
    """
    return {field.name for field in model._meta.fields} | {
        field.name for field in model._meta.many_to_many
    }


def model_property_names(model) -> set[str]:
    """
    The names of the model's properties: the admin shows a property
    where the studio names it, as a table column, an edit page field,
    a read-only field or an export column.
    """
    return {
        name
        for name in dir(model)
        if not name.startswith("_") and isinstance(getattr(model, name, None), property)
    }


def iter_edit_fields(studio):
    """
    Yield the Field objects declared in a model studio's edit_main and
    edit_sidebar, across form sets, groups and layouts.
    """
    all_fields = list(getattr(studio, "edit_main", None) or []) + list(
        getattr(studio, "edit_sidebar", None) or []
    )

    flat_fields = flatten(
        [
            field.get_fields() if hasattr(field, "get_fields") else [field]
            for field in all_fields
        ]
    )

    for field in flat_fields:
        if isinstance(field, Field):
            yield field


def resolvable_name(model, name: str) -> bool:
    """
    Whether a lookup name (possibly traversing relations, like
    'author__name') starts at a model field; 'pk' resolves as Django's
    alias for the primary key.
    """
    try:
        model._meta.get_field(name.split("__")[0])
        return True
    except FieldDoesNotExist:
        return name.split("__")[0] == "pk"


def edit_form_config_errors(studio) -> list[tuple[str, str]]:
    """
    Unresolvable edit form configuration, as (check id, message)
    pairs. A Field naming anything but a model field renders as an
    empty read-only box in the editor — a typo that never surfaces at
    runtime. Widget overrides must be content_studio.widgets classes
    or instances; anything else falls back to the frontend's fallback
    widget silently.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    errors = []
    field_names = (
        model_field_names(model)
        | model_property_names(model)
        | translated_attribute_names(model)
    )

    for field in iter_edit_fields(studio):
        if field.name not in field_names:
            errors.append(
                (
                    "content_studio.E010",
                    f"{studio.__class__.__name__}: edit field {field.name!r} "
                    f"does not exist on {model._meta.label_lower}.",
                )
            )

        if field.widget is not None and not is_kind(field.widget, widgets.BaseWidget):
            errors.append(
                (
                    "content_studio.E010",
                    f"{studio.__class__.__name__}: edit field {field.name!r} "
                    f"has widget {field.widget!r}; widgets must be "
                    "content_studio.widgets classes or instances.",
                )
            )

    return errors


def list_query_errors(studio) -> list[tuple[str, str]]:
    """
    Unresolvable list page configuration, as (check id, message)
    pairs. search_fields and ordering entries that do not start at a
    model field fail the list endpoint with a database FieldError;
    list_filter entries fail every filter with a ParseError; and
    list_item_display values that resolve to neither a field nor a model
    method fail every list-view item with an AttributeError.
    """
    errors = []

    def validate(owner, model):
        if model is None:
            return

        translated = translated_attribute_names(model)

        for entry in getattr(owner, "search_fields", None) or []:
            if entry.lstrip("^=@$") in translated:
                continue

            if not resolvable_name(model, entry):
                errors.append(
                    (
                        "content_studio.E011",
                        f"{config_name(owner)}.search_fields contains "
                        f"{entry!r}, which does not resolve to a field on "
                        f"{model._meta.label_lower}.",
                    )
                )

        for entry in getattr(owner, "ordering", None) or []:
            name = entry[1:] if entry.startswith("-") else entry

            if name == "?" or resolvable_name(model, name):
                continue

            errors.append(
                (
                    "content_studio.E011",
                    f"{config_name(owner)}.ordering contains "
                    f"{entry!r}, which does not resolve to a field on "
                    f"{model._meta.label_lower}.",
                )
            )

        for entry in getattr(owner, "list_filter", None) or []:
            if isinstance(entry, (tuple, list)) and entry:
                entry = entry[0]

            if isinstance(entry, str) and not resolvable_name(model, entry):
                errors.append(
                    (
                        "content_studio.E011",
                        f"{config_name(owner)}.list_filter contains "
                        f"{entry!r}, which does not resolve to a field on "
                        f"{model._meta.label_lower}.",
                    )
                )

        field_names = model_field_names(model)
        display = getattr(owner, "list_item_display", None) or {}

        # A non-mapping here is never a role mapping to validate.
        if isinstance(display, dict):
            for role, value in display.items():
                if value not in field_names and not hasattr(model, value):
                    errors.append(
                        (
                            "content_studio.E011",
                            f"{config_name(owner)}.list_item_display maps "
                            f"{role!r} to {value!r}, which is neither a field "
                            f"nor a method on {model._meta.label_lower}.",
                        )
                    )

    model = getattr(studio, "model", None)
    validate(studio, model)

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline, getattr(inline, "model", None))

    return errors


def duplicate_inline_errors(studio) -> list[tuple[str, str]]:
    """
    The same model inlined twice on one studio, as (check id, message)
    pairs. An inline is served at one endpoint per parent and model, so
    a second inline of the model has no endpoint of its own.
    """
    errors = []
    seen = {}

    for inline in getattr(studio, "inlines", None) or []:
        inline_model = getattr(inline, "model", None)

        if inline_model is None:
            continue

        if inline_model in seen:
            errors.append(
                (
                    "content_studio.E038",
                    f"{inline_model._meta.label_lower} is inlined twice on "
                    f"{studio.__class__.__name__}: {seen[inline_model]} and "
                    f"{inline.__name__}. A model can be inlined once per "
                    "studio; the second inline is not served.",
                )
            )
        else:
            seen[inline_model] = inline.__name__

    return errors


def tenant_field_errors(studio) -> list[tuple[str, str]]:
    """
    A model with more than one foreign key to the tenant model, as
    (check id, message) pairs. Tenant scoping needs one field to scope
    on; with several, every request on the model fails.
    """
    from .utils import get_tenant_field_name

    errors = []
    model = getattr(studio, "model", None)

    if model is None or not cs_settings.TENANT_MODEL:
        return errors

    inline_models = [
        inline.model
        for inline in getattr(studio, "inlines", None) or []
        if getattr(inline, "model", None) is not None
    ]

    for checked in [model, *inline_models]:
        try:
            get_tenant_field_name(checked)
        except ValueError:
            errors.append(
                (
                    "content_studio.E039",
                    f"{checked._meta.label_lower} has more than one foreign "
                    "key to the tenant model; tenant scoping needs exactly "
                    "one.",
                )
            )

    return errors


def inline_fk_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured inline fk_name, as (check id, message) pairs. The
    name must exist on the inline's model and be a foreign key to the
    parent; anything else fails every inline list with a database
    FieldError. An unset fk_name is auto-detected: that needs exactly
    one foreign key to the parent on the inline's model.
    """
    from .utils import get_related_field_name

    errors = []
    model = getattr(studio, "model", None)

    if model is None:
        return errors

    for inline in getattr(studio, "inlines", None) or []:
        fk_name = getattr(inline, "fk_name", None)

        if not fk_name:
            try:
                get_related_field_name(inline, model)
            except ValueError as error:
                errors.append(
                    (
                        "content_studio.E012",
                        f"{inline.__name__}: {error} The inline is not served.",
                    )
                )

            continue

        try:
            field = inline.model._meta.get_field(fk_name)
        except FieldDoesNotExist:
            errors.append(
                (
                    "content_studio.E012",
                    f"{inline.__name__}.fk_name refers to the "
                    f"unknown field {fk_name!r} on "
                    f"{inline.model._meta.label_lower}.",
                )
            )
            continue

        if (
            not (field.many_to_one or field.one_to_one)
            or not field.concrete
            or field.remote_field.model is not model
        ):
            errors.append(
                (
                    "content_studio.E012",
                    f"{inline.__name__}.fk_name must name a "
                    f"foreign key to {model._meta.label_lower}; "
                    f"{fk_name!r} on {inline.model._meta.label_lower} "
                    "is not.",
                )
            )

    return errors


def readonly_fields_errors(studio) -> list[tuple[str, str]]:
    """
    readonly_fields entries that are not model fields, as (check id,
    message) pairs. They would be silently ignored. Inlines are
    checked too.
    """
    errors = []

    def validate(owner, model):
        if model is None:
            return

        field_names = model_field_names(model) | model_property_names(model)

        for name in getattr(owner, "readonly_fields", None) or []:
            if not isinstance(name, str) or name not in field_names:
                errors.append(
                    (
                        "content_studio.E015",
                        f"{config_name(owner)}.readonly_fields entry "
                        f"{name!r} is not a field or property of "
                        f"{model._meta.label_lower}.",
                    )
                )

    validate(studio, getattr(studio, "model", None))

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline, getattr(inline, "model", None))

    return errors


def edit_header_errors(studio) -> list[tuple[str, str]]:
    """
    edit_header entries that are not components, or are text
    components (Title, Subtitle, Text, Callout), as (check id,
    message) pairs: the header only shows components, so fields and
    other values would be silently dropped. Inlines are checked too.
    """
    errors = []

    def validate(owner):
        header = getattr(owner, "edit_header", None) or []

        if isinstance(header, (str, Component)) or not isinstance(
            header, (list, tuple)
        ):
            errors.append(
                (
                    "content_studio.E020",
                    f"{config_name(owner)}.edit_header must be a list of "
                    "components.",
                )
            )
            return

        for entry in header:
            if not isinstance(entry, Component):
                errors.append(
                    (
                        "content_studio.E020",
                        f"{config_name(owner)}.edit_header entry {entry!r} is "
                        "not a component, such as a Button.",
                    )
                )
            elif isinstance(entry, (BaseText, SEOPreview)):
                kind = (
                    "a text component" if isinstance(entry, BaseText) else "a preview"
                )
                errors.append(
                    (
                        "content_studio.E020",
                        f"{config_name(owner)}.edit_header entry {entry!r} is "
                        f"{kind}; the header only shows links and buttons. "
                        "Put it in edit_main or edit_sidebar.",
                    )
                )

    validate(studio)

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline)

    return errors


EDIT_WIDTHS = ("default", "wide")


def edit_width_errors(studio) -> list[tuple[str, str]]:
    """
    An edit_width that is not one of EDIT_WIDTHS, as (check id,
    message) pairs. Inlines are checked too.
    """
    return [
        (
            "content_studio.E024",
            f"{config_name(owner)}.edit_width must be one of "
            f"{', '.join(repr(width) for width in EDIT_WIDTHS)}.",
        )
        for owner in [studio, *(getattr(studio, "inlines", None) or [])]
        if getattr(owner, "edit_width", "default") not in EDIT_WIDTHS
    ]


def view_on_site_errors(studio) -> list[tuple[str, str]]:
    """
    A view_on_site that is neither a boolean nor a method, as (check
    id, message) pairs: anything else would silently turn the edit
    page's "View on site" button on or off.
    """
    if not hasattr(studio, "view_on_site"):
        return []

    value = studio.view_on_site

    if isinstance(value, bool) or callable(value):
        return []

    return [
        (
            "content_studio.E045",
            f"{config_name(studio)}.view_on_site must be True, False or a "
            "method that returns the URL of an object's public page.",
        )
    ]


def preview_errors(studio) -> list[tuple[str, str]]:
    """
    A preview that is not a boolean (E056): anything else would silently
    turn previews of drafts on or off.
    """
    value = getattr(studio, "preview", True)

    if isinstance(value, bool):
        return []

    return [
        (
            "content_studio.E056",
            f"{config_name(studio)}.preview must be True or False.",
        )
    ]


def preview_middleware_warnings() -> list[tuple[str, str]]:
    """
    Shared draft links without PreviewMiddleware (W031): the pages they
    open could be cached by a CDN or indexed, with the link's key in the
    URL.
    """
    if not apps.is_installed("content_studio.previews"):
        return []

    path = "content_studio.previews.middleware.PreviewMiddleware"

    if path in (getattr(settings, "MIDDLEWARE", None) or []):
        return []

    return [
        (
            "content_studio.W031",
            "content_studio.previews is installed, but MIDDLEWARE has no "
            f"{path}: pages opened with a shared draft link may be cached "
            "or indexed. Add it to MIDDLEWARE.",
        )
    ]


def duplication_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured duplicate_inlines, as (check id, message) pairs: it
    must be a list of inlines from the studio's `inlines`; any other
    entry would never be copied.
    """
    errors = []
    duplicate_inlines = getattr(studio, "duplicate_inlines", None) or []
    inlines = list(getattr(studio, "inlines", None) or [])
    name = config_name(studio)

    if not isinstance(duplicate_inlines, (list, tuple)):
        return [
            (
                "content_studio.E021",
                f"{name}.duplicate_inlines must be a list of inlines.",
            )
        ]

    for entry in duplicate_inlines:
        if entry not in inlines:
            label = entry.__name__ if isinstance(entry, type) else repr(entry)
            errors.append(
                (
                    "content_studio.E021",
                    f"{name}.duplicate_inlines entry {label} is not one of "
                    f"{name}.inlines.",
                )
            )

    return errors


def duplication_warnings(studio) -> list[tuple[str, str]]:
    """
    Duplication options without effect, as (check id, message) pairs:
    singletons are never duplicated, and duplicate_inlines only applies
    with allow_duplication.
    """
    name = config_name(studio)

    if getattr(studio, "allow_duplication", False) and get_is_singleton(studio):
        return [
            (
                "content_studio.W014",
                f"{name}.allow_duplication has no effect: singletons cannot "
                "be duplicated.",
            )
        ]

    if getattr(studio, "duplicate_inlines", None) and not getattr(
        studio, "allow_duplication", False
    ):
        return [
            (
                "content_studio.W014",
                f"{name}.duplicate_inlines has no effect without " "allow_duplication.",
            )
        ]

    return []


def recover_changes_warnings(studio) -> list[tuple[str, str]]:
    """
    A recover_changes_exclude that keeps nothing out, as (check id,
    message) pairs: not a list of field names, or names that are not
    fields of the model, so their unsaved values are kept after all.
    """
    exclude = getattr(studio, "recover_changes_exclude", None)
    name = config_name(studio)

    if not exclude:
        return []

    if not isinstance(exclude, (list, tuple)) or not all(
        isinstance(entry, str) for entry in exclude
    ):
        return [
            (
                "content_studio.W029",
                f"{name}.recover_changes_exclude must be a list of field names.",
            )
        ]

    fields = {field.name for field in studio.model._meta.get_fields()}
    unknown = [entry for entry in exclude if entry not in fields]

    if unknown:
        return [
            (
                "content_studio.W029",
                f"{name}.recover_changes_exclude names {unknown!r}, which "
                f"{'is not a field' if len(unknown) == 1 else 'are not fields'} "
                f"of {studio.model._meta.label}. Their unsaved values are kept "
                "in the browser.",
            )
        ]

    return []


def export_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured export_fields, as (check id, message) pairs: a list
    of unique field names or TableColumn objects, each a forward model
    field, __str__ or a method on the studio. allow_export exports the
    table_display columns, which are checked as table_display (E006).
    """
    export_fields = getattr(studio, "export_fields", None)
    name = config_name(studio)

    if export_fields is None:
        return []

    if not isinstance(export_fields, (list, tuple)):
        return [
            (
                "content_studio.E022",
                f"{name}.export_fields must be a list of field names or "
                "TableColumn objects.",
            )
        ]

    errors = []
    seen = set()
    model = studio.model

    for entry in export_fields:
        if isinstance(entry, str):
            column = TableColumn(field=entry)
        elif isinstance(entry, TableColumn):
            column = entry
        else:
            errors.append(
                (
                    "content_studio.E022",
                    f"{name}.export_fields entries must be field names or "
                    f"TableColumn objects; got {entry!r}.",
                )
            )
            continue

        if column.field in seen:
            errors.append(
                (
                    "content_studio.E022",
                    f"{name}.export_fields contains {column.field!r} more "
                    "than once.",
                )
            )
        seen.add(column.field)

        if (
            column.field == "__str__"
            or is_computed_column(studio, column)
            or column.field in model_property_names(model)
        ):
            continue

        try:
            field = model._meta.get_field(column.field)
        except FieldDoesNotExist:
            field = None

        if field is None or (field.auto_created and not field.concrete):
            errors.append(
                (
                    "content_studio.E022",
                    f"{name}.export_fields entry {column.field!r} does not "
                    "resolve to a model field, a model property, __str__ or "
                    "a method on the studio.",
                )
            )

    return errors


def export_warnings(studio) -> list[tuple[str, str]]:
    """
    Export options without effect, as (check id, message) pairs:
    singletons are never exported, an empty export_fields enables
    nothing, and columns in exclude are left out of the export.
    """
    name = config_name(studio)
    export_fields = getattr(studio, "export_fields", None)
    enabled = bool(export_fields) or bool(getattr(studio, "allow_export", False))

    if enabled and get_is_singleton(studio):
        option = "export_fields" if export_fields else "allow_export"
        return [
            (
                "content_studio.W015",
                f"{name}.{option} has no effect: singletons cannot be " "exported.",
            )
        ]

    if isinstance(export_fields, (list, tuple)) and not export_fields:
        return [
            (
                "content_studio.W015",
                f"{name}.export_fields is empty, which offers no export. "
                "Remove it, or set allow_export to export the table_display "
                "columns.",
            )
        ]

    if not enabled or not isinstance(export_fields or [], (list, tuple)):
        return []

    excluded = set(getattr(studio, "exclude", None) or [])
    entries = export_fields or resolve_table_display(studio)
    option = "export_fields" if export_fields else "table_display"
    warnings = []

    for entry in entries:
        field_name = entry.field if isinstance(entry, TableColumn) else entry

        if isinstance(field_name, str) and field_name in excluded:
            warnings.append(
                (
                    "content_studio.W015",
                    f"{name}.{option} column {field_name!r} is in exclude "
                    "and is left out of the export.",
                )
            )

    return warnings


def _import_writable_error(studio, field, form_names) -> str | None:
    """Why a file cannot set a model field, or None."""
    from .admin import get_write_only_field_names

    if field.primary_key:
        return "is the primary key, which is never imported"

    if field.auto_created and not field.concrete:
        return "is a reverse relation"

    if isinstance(field, models.FileField):
        return "is a file field, which cannot be imported"

    if field.name == get_tenant_field_name(studio.model):
        return "is the tenant field, which comes from the selected tenant"

    if field.name in get_write_only_field_names(studio, studio.model):
        return "has a write-only PasswordWidget"

    if field.name not in form_names:
        return "is not a field the edit page writes"

    if field.name in set(getattr(studio, "readonly_fields", None) or []):
        return "is read-only"

    return None


def import_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured import, as (check id, message) pairs: import_fields
    must name model fields the edit page writes; import_id_fields must
    name model fields, the ones other than the primary key among the
    import fields; import_lookups must map relation fields to fields of
    the related model.
    """
    from .importing import get_import_fields

    name = config_name(studio)
    model = studio.model
    errors = []
    import_fields = getattr(studio, "import_fields", None)
    id_fields = getattr(studio, "import_id_fields", None)
    lookups = getattr(studio, "import_lookups", None)
    enabled = bool(import_fields) or bool(getattr(studio, "allow_import", False))

    if import_fields is not None and (
        not isinstance(import_fields, (list, tuple))
        or not all(isinstance(entry, str) for entry in import_fields)
    ):
        return [
            (
                "content_studio.E048",
                f"{name}.import_fields must be a list of field names.",
            )
        ]

    if id_fields is not None and (
        not isinstance(id_fields, (list, tuple))
        or not all(isinstance(entry, str) for entry in id_fields)
    ):
        errors.append(
            (
                "content_studio.E048",
                f"{name}.import_id_fields must be a list of field names.",
            )
        )
        id_fields = None

    if lookups is not None and (
        not isinstance(lookups, dict)
        or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in lookups.items()
        )
    ):
        errors.append(
            (
                "content_studio.E048",
                f"{name}.import_lookups must map field names to field names "
                "of the related model.",
            )
        )
        lookups = None

    if not enabled:
        return errors

    form_names = edit_form_field_names(studio)
    seen = set()

    for entry in import_fields or []:
        if entry in seen:
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_fields contains {entry!r} more than once.",
                )
            )
            continue

        seen.add(entry)

        try:
            field = model._meta.get_field(entry)
        except FieldDoesNotExist:
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_fields entry {entry!r} is not a field of "
                    f"{model._meta.label}.",
                )
            )
            continue

        reason = _import_writable_error(studio, field, form_names)

        if reason:
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_fields entry {entry!r} {reason}.",
                )
            )

    importable = {field.name for field in get_import_fields(studio, None)}
    importable &= form_names

    for entry in id_fields or []:
        try:
            field = model._meta.get_field(entry)
        except FieldDoesNotExist:
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_id_fields entry {entry!r} is not a field "
                    f"of {model._meta.label}.",
                )
            )
            continue

        if field.many_to_many or (field.auto_created and not field.concrete):
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_id_fields entry {entry!r} must be a "
                    "concrete field.",
                )
            )
        elif not field.primary_key and entry not in importable:
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_id_fields entry {entry!r} must be an "
                    "import field too, so rows without a match can be created.",
                )
            )

    for entry, lookup in (lookups or {}).items():
        try:
            field = model._meta.get_field(entry)
        except FieldDoesNotExist:
            field = None

        if (
            field is None
            or not field.is_relation
            or (field.auto_created and not field.concrete)
        ):
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_lookups key {entry!r} is not a foreign "
                    "key or many-to-many field.",
                )
            )
            continue

        if lookup == "pk":
            continue

        try:
            field.related_model._meta.get_field(lookup)
        except FieldDoesNotExist:
            errors.append(
                (
                    "content_studio.E048",
                    f"{name}.import_lookups[{entry!r}] names {lookup!r}, "
                    f"which is not a field of {field.related_model._meta.label}.",
                )
            )

    return errors


def _is_unique_together(model, names: list[str]) -> bool:
    """Whether a model's values for these fields are unique."""
    names = set(names)

    if len(names) == 1:
        try:
            field = model._meta.get_field(next(iter(names)))
        except FieldDoesNotExist:
            return False

        if field.primary_key or field.unique:
            return True

    for unique_together in model._meta.unique_together:
        if set(unique_together) <= names:
            return True

    for constraint in model._meta.constraints:
        if (
            isinstance(constraint, models.UniqueConstraint)
            and constraint.fields
            and constraint.condition is None
            and set(constraint.fields) <= names
        ):
            return True

    return False


def import_warnings(studio) -> list[tuple[str, str]]:
    """
    Import options without effect or with surprises, as (check id,
    message) pairs: singletons are never imported, an empty
    import_fields enables nothing, and rows are matched on fields that
    need not be unique.
    """
    name = config_name(studio)
    import_fields = getattr(studio, "import_fields", None)
    enabled = bool(import_fields) or bool(getattr(studio, "allow_import", False))

    if enabled and get_is_singleton(studio):
        option = "import_fields" if import_fields else "allow_import"
        return [
            (
                "content_studio.W026",
                f"{name}.{option} has no effect: singletons cannot be imported.",
            )
        ]

    if isinstance(import_fields, (list, tuple)) and not import_fields:
        return [
            (
                "content_studio.W026",
                f"{name}.import_fields is empty, which offers no import. "
                "Remove it, or set allow_import to import the fields the "
                "edit page writes.",
            )
        ]

    if not enabled:
        return []

    model = studio.model
    warnings = []
    id_fields = getattr(studio, "import_id_fields", None)

    if isinstance(id_fields, (list, tuple)) and id_fields:
        try:
            for entry in id_fields:
                model._meta.get_field(entry)
        except (FieldDoesNotExist, TypeError):
            id_fields = None

        if id_fields and not _is_unique_together(model, list(id_fields)):
            warnings.append(
                (
                    "content_studio.W026",
                    f"{name}.import_id_fields {list(id_fields)!r} need not be "
                    "unique: a row that matches more than one object fails. "
                    "Use a unique field or a unique set of fields.",
                )
            )

    return warnings


# Fields a prepopulated value cannot go into, as in the classic admin.
PREPOPULATED_TARGET_EXCLUDED = (
    models.DateTimeField,
    models.ForeignKey,
    models.OneToOneField,
    models.ManyToManyField,
)


def prepopulated_fields_errors(studio) -> list[tuple[str, str]]:
    """
    Misconfigured prepopulated_fields, as (check id, message) pairs:
    not a mapping, a target that is not a field (or a field that cannot
    take a slug-like value), sources that are not fields, or a target
    that is read-only, so the filled-in value is never saved. Inlines
    are checked too.
    """
    errors = []

    def error(owner, message):
        errors.append(("content_studio.E016", f"{config_name(owner)}.{message}"))

    def validate(owner, model):
        if model is None:
            return

        prepopulated = getattr(owner, "prepopulated_fields", None) or {}

        if not isinstance(prepopulated, dict):
            error(owner, "prepopulated_fields must be a mapping of field names.")
            return

        readonly = set(getattr(owner, "readonly_fields", None) or [])

        for target, sources in prepopulated.items():
            try:
                field = model._meta.get_field(target)
            except (FieldDoesNotExist, TypeError):
                error(
                    owner,
                    f"prepopulated_fields refers to {target!r}, which is not "
                    f"a field of {model._meta.label_lower}.",
                )
                continue

            if isinstance(field, PREPOPULATED_TARGET_EXCLUDED):
                error(
                    owner,
                    f"prepopulated_fields refers to {target!r}, which must "
                    "not be a DateTimeField, ForeignKey, OneToOneField or "
                    "ManyToManyField.",
                )

            if target in readonly:
                error(
                    owner,
                    f"prepopulated_fields refers to {target!r}, which is in "
                    "readonly_fields, so the filled-in value is never saved.",
                )

            if isinstance(sources, str) or not isinstance(sources, (list, tuple)):
                error(
                    owner,
                    f"prepopulated_fields[{target!r}] must be a list or "
                    "tuple of field names.",
                )
                continue

            field_names = model_field_names(model)

            for source in sources:
                if source not in field_names:
                    error(
                        owner,
                        f"prepopulated_fields[{target!r}] refers to "
                        f"{source!r}, which is not a field of "
                        f"{model._meta.label_lower}.",
                    )

    validate(studio, getattr(studio, "model", None))

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline, getattr(inline, "model", None))

    return errors


def mapping_errors(site) -> list[tuple[str, str]]:
    """
    Widget and format mapping values that are not widget or format
    classes or instances, as (check id, message) pairs. Both mappings are
    serialized to the frontend by name; anything else fails the info
    endpoint or renders nothing at all.
    """
    errors = []

    for key, widget in (getattr(site, "default_widget_mapping", None) or {}).items():
        if not is_kind(widget, widgets.BaseWidget):
            errors.append(
                (
                    "content_studio.E013",
                    f"default_widget_mapping[{key!r}] must map to a "
                    "content_studio.widgets class or instance.",
                )
            )

    for key, frmt in (getattr(site, "default_format_mapping", None) or {}).items():
        if not is_kind(frmt, formats.BaseFormat):
            errors.append(
                (
                    "content_studio.E013",
                    f"default_format_mapping[{key!r}] must map to a "
                    "content_studio.formats class or instance.",
                )
            )

    return errors


def readonly_required_warnings(studio) -> list[tuple[str, str]]:
    """
    Required model fields configured readonly in the edit form, as
    (check id, message) pairs. The value can never be provided, so
    every save fails validation — the same failure W001 reports for
    fields left out entirely.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    ignored = ignored_edit_field_names(model)
    required = {
        field.name
        for field in model._meta.get_fields()
        if is_required_model_field(field) and field.name not in ignored
    }

    warnings = []

    for name in getattr(studio, "readonly_fields", None) or []:
        if name in required:
            warnings.append(
                (
                    "content_studio.W002",
                    f"{studio.__class__.__name__}: the required field "
                    f"{name!r} is in readonly_fields, so creating objects "
                    "will fail validation. Remove it from readonly_fields "
                    "(override get_readonly_fields to make it read-only "
                    "once the object exists), or give the model field a "
                    "default, make it nullable or blank.",
                )
            )

    for field in iter_edit_fields(studio):
        if field.readonly and field.name in required:
            warnings.append(
                (
                    "content_studio.W002",
                    f"{studio.__class__.__name__}: the required field "
                    f"{field.name!r} is configured readonly in the edit "
                    "form, so saving objects will fail validation. Make the "
                    "field editable in the form, or give the model field a "
                    "default, make it nullable or blank.",
                )
            )

    return warnings


def field_has_choices(model_field) -> bool:
    """
    Whether a model field gives the admin choices to render: Django's
    choices, or the choices a Content Studio field (such as
    MultipleChoiceField with its options) sends in its field attributes.
    """
    if getattr(model_field, "choices", None):
        return True

    get_attributes = getattr(model_field, "cs_get_field_attributes", None)

    if not callable(get_attributes):
        return False

    try:
        return bool(get_attributes().get("choices"))
    except Exception:
        return False


def choice_widget_warnings(studio) -> list[tuple[str, str]]:
    """
    Choice-driven widgets on fields without choices, as (check id,
    message) pairs. Selects and toggle groups render their options
    from the field's choices; without any, they render empty.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    fields = {field.name: field for field in model._meta.get_fields()}
    warnings = []

    def is_choice_widget(widget) -> bool:
        return is_kind(widget, CHOICE_WIDGETS)

    for field in iter_edit_fields(studio):
        model_field = fields.get(field.name)

        if model_field is None:
            continue

        # The widget override, or a widget_class set on the model field.
        widget = field.widget or getattr(model_field, "widget_class", None)

        if is_choice_widget(widget) and not field_has_choices(model_field):
            warnings.append(
                (
                    "content_studio.W003",
                    f"{studio.__class__.__name__}: the widget "
                    f"{as_instance(widget).__class__.__name__} on "
                    f"{field.name!r} renders choices, "
                    f"but the field on {model._meta.label_lower} has none.",
                )
            )

    return warnings


def cover_image_widget_warnings(studio) -> list[tuple[str, str]]:
    """
    CoverImageWidget on a field that is not a single relation to the
    media library model, as (check id, message) pairs. The widget
    edits one media item; on any other field it has nothing to show.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    fields = {field.name: field for field in model._meta.get_fields()}
    media_model = cs_settings.MEDIA_LIBRARY_MODEL
    warnings = []

    for field in iter_edit_fields(studio):
        model_field = fields.get(field.name)

        if model_field is None:
            continue

        widget = field.widget or getattr(model_field, "widget_class", None)

        if not is_kind(widget, widgets.CoverImageWidget):
            continue

        is_media_relation = (
            media_model is not None
            and isinstance(model_field, models.ForeignKey)
            and model_field.related_model is media_model
        )

        if not is_media_relation:
            warnings.append(
                (
                    "content_studio.W019",
                    f"{studio.__class__.__name__}: CoverImageWidget on "
                    f"{field.name!r} edits a media item, but the field on "
                    f"{model._meta.label_lower} is not a MediaField to the "
                    "media library model.",
                )
            )

    return warnings


def sortable_by_warnings(studio) -> list[tuple[str, str]]:
    """
    sortable_by entries that are not table columns, as (check id,
    message) pairs. The sort UI attaches to the table's headers, so a
    name without a column is silently dead configuration.
    """
    sortable_by = getattr(studio, "sortable_by", None)

    if not sortable_by:
        return []

    columns = {column.field for column in get_table_display_columns(studio)}
    warnings = []

    for name in sortable_by:
        if name not in columns:
            warnings.append(
                (
                    "content_studio.W004",
                    f"{studio.__class__.__name__}.sortable_by contains "
                    f"{name!r}, which is not a column in table_display; "
                    "the sort UI only attaches to table columns.",
                )
            )

    return warnings


def reorder_ordering_warnings(studio) -> list[tuple[str, str]]:
    """
    An ordering that contradicts reorder_field, as (check id, message)
    pairs. A reorderable list must be ordered by its reorder field
    (after any reorder_scope fields), or moves land somewhere other
    than where they were dropped. Inlines are checked too.
    """
    warnings = []

    def validate(owner):
        field_name = getattr(owner, "reorder_field", None)
        ordering = list(getattr(owner, "ordering", None) or [])

        if not field_name or not ordering:
            return

        scope = set(getattr(owner, "reorder_scope", None) or [])
        rest = list(ordering)
        while rest and rest[0] in scope:
            rest.pop(0)

        if not rest or rest[0] != field_name:
            warnings.append(
                (
                    "content_studio.W013",
                    f"{config_name(owner)}.ordering does not start with its "
                    f"reorder_field {field_name!r}, so reordering does not "
                    "match the order of the list.",
                )
            )

    validate(studio)

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline)

    return warnings


def list_filter_entry_warnings(studio) -> list[tuple[str, str]]:
    """
    list_filter entries that are (partly) ignored, as (check id,
    message) pairs. Field paths, ListFilter classes and Django's
    SimpleListFilter classes are filters; a (field, class) tuple filters
    on its field with the default control, without the class; anything
    else (such as Django's field list filter classes) is ignored.
    """
    from .filters import is_django_simple_list_filter, is_list_filter_class

    warnings = []

    for entry in getattr(studio, "list_filter", None) or []:
        if isinstance(entry, str):
            continue

        if is_list_filter_class(entry) or is_django_simple_list_filter(entry):
            continue

        if isinstance(entry, (tuple, list)) and entry and isinstance(entry[0], str):
            warnings.append(
                (
                    "content_studio.W005",
                    f"{config_name(studio)}.list_filter contains {entry!r}: "
                    f"{entry[0]!r} gets its default filter and the filter "
                    "class is ignored. Use the field name, or a ListFilter "
                    "class for a filter of your own.",
                )
            )
            continue

        warnings.append(
            (
                "content_studio.W005",
                f"{config_name(studio)}.list_filter contains {entry!r}, "
                "which is ignored: entries are field names, paths across "
                "relations ('author__country') or ListFilter classes.",
            )
        )

    return warnings


def list_filter_errors(studio) -> list[tuple[str, str]]:
    """
    list_filter entries that resolve but cannot work, as (check id,
    message) pairs. E042: a path that reads or crosses a protected field
    (one the model's studio excludes, or the user model's password) or
    continues past a field that is not a relation; the list refuses
    such filters. E043: a custom filter without a title or
    parameter_name, without queryset(), or whose parameter_name is
    taken by a field filter, another custom filter or a reserved query
    parameter.
    """
    from .filters import (
        FilterPathError,
        LookupFilter,
        ListFilter,
        is_django_simple_list_filter,
        is_list_filter_class,
        resolve_filter_path,
    )

    errors = []

    def validate(owner, model):
        if model is None:
            return

        name = config_name(owner)
        paths = []
        custom = []

        for entry in getattr(owner, "list_filter", None) or []:
            if isinstance(entry, (tuple, list)) and entry:
                entry = entry[0]

            if isinstance(entry, str):
                if not resolvable_name(model, entry):
                    # E011 reports it.
                    continue
                paths.append(entry)
                try:
                    resolve_filter_path(model, entry, owner)
                except FilterPathError as error:
                    errors.append(
                        (
                            "content_studio.E042",
                            f"{name}.list_filter contains {error}",
                        )
                    )
            elif is_list_filter_class(entry) or is_django_simple_list_filter(entry):
                custom.append(entry)

        taken = set(paths) | set(LookupFilter.NON_FILTER_FIELDS)

        for filter_class in custom:
            label = f"{name}.list_filter contains {filter_class.__name__}"
            parameter = getattr(filter_class, "parameter_name", None)

            if not getattr(filter_class, "title", None):
                errors.append(("content_studio.E043", f"{label}, which has no title."))

            if not parameter:
                errors.append(
                    (
                        "content_studio.E043",
                        f"{label}, which has no parameter_name.",
                    )
                )
                continue

            if (
                is_list_filter_class(filter_class)
                and filter_class.queryset is ListFilter.queryset
            ):
                errors.append(
                    (
                        "content_studio.E043",
                        f"{label}, which does not implement queryset().",
                    )
                )

            if (
                parameter in taken
                or parameter.startswith(LookupFilter.EXCLUDE_SYMBOL)
                or any(parameter.startswith(f"{path}__") for path in paths)
            ):
                errors.append(
                    (
                        "content_studio.E043",
                        f"{label}, whose parameter_name {parameter!r} is "
                        "already a field filter, another filter's or a "
                        "reserved query parameter.",
                    )
                )

            taken.add(parameter)

    validate(studio, getattr(studio, "model", None))

    for inline in getattr(studio, "inlines", None) or []:
        validate(inline, getattr(inline, "model", None))

    return errors


def table_edit_errors(studio) -> list[tuple[str, str]]:
    """
    A misconfigured table_edit (or list_editable), as (check id, message)
    pairs (E057): each name must be a table_display column, a model field
    a table cell can edit, written by the edit page and not read-only,
    and not the first column, which opens the object (like the Django
    admin's list_editable).
    """
    from .table_edit import cell_field_error, declared_table_edit, link_column

    names = declared_table_edit(studio)
    attribute = "table_edit" if declares(studio, "table_edit") else "list_editable"
    owner = f"{studio.__class__.__name__}.{attribute}"

    if not isinstance(getattr(studio, attribute, None), (list, tuple)):
        if attribute == "table_edit":
            return [("content_studio.E057", f"{owner} must be a list of field names.")]

        return []

    if not names:
        return []

    errors = []
    columns = {column.field for column in get_table_display_columns(studio)}

    try:
        form_names = edit_form_field_names(studio)
    except Exception:
        form_names = None

    readonly = set(getattr(studio, "readonly_fields", None) or [])
    link = link_column(studio)

    for name in names:
        if not isinstance(name, str):
            errors.append(
                (
                    "content_studio.E057",
                    f"{owner} entries must be field names; got {name!r}.",
                )
            )
            continue

        reason = None

        if name not in columns:
            reason = "is not a table_display column"
        elif name == link:
            reason = (
                "is the first table_display column, which opens the object; "
                "put another column first"
            )
        else:
            reason = cell_field_error(studio, name)

        if reason is None and form_names is not None and name not in form_names:
            reason = "is not a field the edit page writes"

        if reason is None and name in readonly:
            reason = "is read-only"

        if reason:
            errors.append(
                ("content_studio.E057", f"{owner} has {name!r}, which {reason}.")
            )

    return errors


def table_edit_warnings(studio) -> list[tuple[str, str]]:
    """
    Inline editing that does not show, or the Django admin's name for it
    (W032).
    """
    from .table_edit import declared_table_edit

    warnings = []
    name = studio.__class__.__name__

    if isinstance(getattr(studio, "list_editable", None), (list, tuple)):
        if declares(studio, "table_edit"):
            message = (
                f"{name}.list_editable is ignored because table_edit is set; "
                "remove list_editable."
            )
        else:
            message = (
                f"{name}.list_editable is the Django admin's name for the "
                "columns edited in place; rename it to table_edit."
            )

        warnings.append(("content_studio.W032", message))

    if declared_table_edit(studio) and "table" not in (
        getattr(studio, "list_views", None) or []
    ):
        warnings.append(
            (
                "content_studio.W032",
                f"{name} edits columns in place, but list_views does not "
                "offer the table view, the only view that edits in place.",
            )
        )

    return warnings


def list_display_warnings(studio) -> list[tuple[str, str]]:
    """
    Django admin naming on a studio, as (check id, message) pairs.
    list_display works as an alias of table_display but should be
    renamed; get_list_display is no longer called since the list view
    hook is get_list_item_display.
    """
    warnings = []

    for owner in [studio, *(getattr(studio, "inlines", None) or [])]:
        if isinstance(getattr(owner, "list_display", None), (list, tuple)):
            if declares(owner, "table_display"):
                message = (
                    f"{config_name(owner)}.list_display is ignored because "
                    "table_display is set; remove list_display."
                )
            else:
                message = (
                    f"{config_name(owner)}.list_display is the Django "
                    "admin's name for the table columns; rename it to "
                    "table_display."
                )

            warnings.append(("content_studio.W010", message))

    if declares(studio, "get_list_display"):
        warnings.append(
            (
                "content_studio.W011",
                f"{studio.__class__.__name__}.get_list_display is not "
                "called; the list view's hook is get_list_item_display.",
            )
        )

    return warnings


BUILT_IN_WIDGET_TYPES = {
    "ActivityLogWidget",
    "ContentListWidget",
    "NotificationsWidget",
    "ReviewQueue",
    "ScheduledTasksWidget",
    "SpacingWidget",
    "StatisticWidget",
}


def iter_dashboard_widgets(site):
    """The widgets of the site dashboard and of the dashboard pages."""
    dashboard = getattr(site, "dashboard", None)

    yield from getattr(dashboard, "widgets", None) or []

    for extension in getattr(site, "extensions", None) or []:
        if isinstance(extension, DashboardPage):
            yield from getattr(extension.dashboard, "widgets", None) or []


# The first path segments of the admin's own pages, which a dashboard
# page's path cannot use.
RESERVED_PAGE_PATHS = {
    "content",
    "media-library",
    "notifications",
    "login",
    "forgot-password",
    "reset-password",
    "set-password",
}


def dashboard_page_errors(site) -> list[tuple[str, str]]:
    """
    Dashboard pages and widgets the admin cannot show, as (check id,
    message) pairs: a page path taken by one of the admin's own pages,
    and refresh intervals that are not a positive number of seconds.
    """
    errors = []

    for extension in getattr(site, "extensions", None) or []:
        if not isinstance(extension, DashboardPage):
            continue

        segment = str(extension.path).strip("/").split("/")[0]

        if not segment or segment in RESERVED_PAGE_PATHS:
            errors.append(
                (
                    "content_studio.E028",
                    f"The dashboard page path {extension.path!r} is taken by "
                    "one of the admin's own pages; choose another path.",
                )
            )

    for widget in iter_dashboard_widgets(site):
        interval = getattr(widget, "refresh_interval", None)

        if interval is not None and (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
        ):
            errors.append(
                (
                    "content_studio.E029",
                    f"The dashboard widget {widget.__class__.__name__} has "
                    f"refresh_interval {interval!r}; set it to a positive "
                    "number of seconds or None.",
                )
            )

    return errors


def dashboard_widget_warnings(site) -> list[tuple[str, str]]:
    """
    Dashboard widgets the admin cannot show, as (check id, message)
    pairs: only the built-in widget types have a display, so a widget
    that does not subclass one of them shows nothing, and the
    notifications widget needs the notifications app.
    """
    warnings = []

    for widget in iter_dashboard_widgets(site):
        widget_type = getattr(widget, "widget_type", None)

        if widget_type == "NotificationsWidget" and not apps.is_installed(
            "content_studio.notifications"
        ):
            warnings.append(
                (
                    "content_studio.W021",
                    f"The dashboard widget {widget.__class__.__name__} shows "
                    "notifications, but content_studio.notifications is not in "
                    "INSTALLED_APPS; it is not shown.",
                )
            )
        elif widget_type == "ReviewQueue" and not apps.is_installed(
            "content_studio.review"
        ):
            warnings.append(
                (
                    "content_studio.W021",
                    f"The dashboard widget {widget.__class__.__name__} shows "
                    "review requests, but content_studio.review is not in "
                    "INSTALLED_APPS; it is not shown.",
                )
            )
        elif widget_type not in BUILT_IN_WIDGET_TYPES:
            warnings.append(
                (
                    "content_studio.W012",
                    f"The dashboard widget {widget.__class__.__name__} is not "
                    "a built-in widget type and is not shown; subclass one of "
                    "the built-in widgets, such as StatisticWidget.",
                )
            )

    return warnings


def task_adapter_warnings(site) -> list[tuple[str, str]]:
    """
    The warnings of the task adapters behind the dashboard widgets, as
    (check id, message) pairs, once per adapter.
    """
    warnings = []
    seen = set()

    for widget in iter_dashboard_widgets(site):
        adapter = getattr(widget, "adapter", None)
        check = getattr(adapter, "check", None)

        if not callable(check) or id(adapter) in seen:
            continue
        seen.add(id(adapter))
        warnings.extend(check())

    # The status page's adapters: the registered ones, or Huey's.
    from django.apps import apps

    if apps.is_installed("content_studio.contrib.status"):
        from .contrib.status.tasks import get_adapters

        for adapter in get_adapters():
            if id(adapter) not in seen:
                seen.add(id(adapter))
                warnings.extend(adapter.check())

    return warnings


def analytics_errors(site) -> list[tuple[str, str]]:
    """
    Analytics the admin cannot show, as (check id, message) pairs: an
    analytics page, link, component or widget without an
    AnalyticsExtension, more than one AnalyticsExtension, a provider
    reporting metrics or breakdowns Content Studio does not know, and an
    analytics page path taken by another page.
    """
    from .analytics import (
        Analytics,
        AnalyticsExtension,
        AnalyticsLink,
        AnalyticsPage,
        AnalyticsStatisticWidget,
        AnalyticsTopPagesWidget,
    )
    from .analytics.providers import BREAKDOWNS, METRICS

    errors = []
    extensions = list(getattr(site, "extensions", None) or [])
    analytics = [e for e in extensions if isinstance(e, AnalyticsExtension)]
    pages = [e for e in extensions if isinstance(e, AnalyticsPage)]

    if len(analytics) > 1:
        errors.append(
            (
                "content_studio.E037",
                "The site has more than one AnalyticsExtension; keep one.",
            )
        )

    if len(pages) > 1:
        errors.append(
            (
                "content_studio.E037",
                "The site has more than one AnalyticsPage; keep one.",
            )
        )

    if not analytics:
        users = [
            e.__class__.__name__
            for e in extensions
            if isinstance(e, (AnalyticsPage, AnalyticsLink))
        ]
        users += [
            w.__class__.__name__
            for w in iter_dashboard_widgets(site)
            if isinstance(w, (AnalyticsStatisticWidget, AnalyticsTopPagesWidget))
        ]
        users += [
            f"{studio.__class__.__name__}'s {c.__class__.__name__}"
            for studio in site._registry.values()
            for c in iter_components(studio)
            if isinstance(c, Analytics)
        ]

        for name in dict.fromkeys(users):
            errors.append(
                (
                    "content_studio.E037",
                    f"{name} shows analytics, but the site has no "
                    "AnalyticsExtension; add one to its extensions.",
                )
            )
    else:
        provider = analytics[0].provider
        unknown = [m for m in provider.metrics if m not in METRICS] + [
            b for b in provider.breakdowns if b not in BREAKDOWNS
        ]

        if unknown:
            errors.append(
                (
                    "content_studio.E037",
                    f"The analytics provider {provider.__class__.__name__} reports "
                    f"{', '.join(map(repr, unknown))}, which Content Studio does "
                    "not know.",
                )
            )

    taken = {str(e.path).strip("/") for e in extensions if isinstance(e, DashboardPage)}

    for page in pages:
        path = str(page.path).strip("/")

        if path.split("/")[0] in RESERVED_PAGE_PATHS or path in taken:
            errors.append(
                (
                    "content_studio.E037",
                    f"The analytics page path {page.path!r} is taken by another "
                    "page; choose another path.",
                )
            )

    return errors


def analytics_warnings(site) -> list[tuple[str, str]]:
    """The analytics provider's own warnings, as (check id, message) pairs."""
    from .analytics import get_analytics

    analytics = get_analytics(site)

    return list(analytics.provider.check()) if analytics else []


def model_group_warnings(site) -> list[tuple[str, str]]:
    """
    Model groups listing unregistered models, as (check id, message)
    pairs. The model groups drive the menu; an unregistered model
    renders a dead entry.
    """
    warnings = []

    for group in getattr(site, "model_groups", None) or []:
        for model in group.models:
            if not site.is_registered(model):
                warnings.append(
                    (
                        "content_studio.W006",
                        f"The model group {group.name!r} lists "
                        f"{model._meta.label_lower}, which is not "
                        "registered with the site; register it or remove it "
                        "from the group.",
                    )
                )

    return warnings


def media_library_warnings() -> list[tuple[str, str]]:
    """
    Media library models missing the documented contract fields, as
    (check id, message) pairs. Uploads, previews, search and folders
    rely on them; tags stays optional.
    """
    warnings = []

    def missing_fields(model, names):
        field_names = {field.name for field in model._meta.get_fields()}

        return [name for name in names if name not in field_names]

    media_model = cs_settings.MEDIA_LIBRARY_MODEL

    if media_model:
        missing = missing_fields(media_model, MEDIA_MODEL_FIELDS)

        if missing:
            warnings.append(
                (
                    "content_studio.W007",
                    f"The media library model {media_model._meta.label_lower} "
                    f"misses the field(s) {', '.join(missing)}; the library "
                    "expects file, name and type fields.",
                )
            )

    folder_model = cs_settings.MEDIA_LIBRARY_FOLDER_MODEL

    if folder_model:
        missing = missing_fields(folder_model, MEDIA_FOLDER_MODEL_FIELDS)

        if missing:
            warnings.append(
                (
                    "content_studio.W007",
                    f"The media folder model {folder_model._meta.label_lower} "
                    f"misses the field(s) {', '.join(missing)}; the library "
                    "expects name and parent fields.",
                )
            )

    return warnings


def crop_hook_warnings() -> list[tuple[str, str]]:
    """
    A crop_image hook without a media library, as (check id, message)
    pairs. The hook can only run against media items; without a media
    model it is dead code.
    """
    site = cs_settings.ADMIN_SITE
    hook = getattr(site, "crop_image", None)
    # The built-in crop_image is not the site's own: it is simply off.
    own = callable(hook) and getattr(hook, "__func__", None) is not getattr(
        ContentStudioSite, "crop_image", None
    )

    if own and not cs_settings.MEDIA_LIBRARY_MODEL:
        return [
            (
                "content_studio.W008",
                "The admin site defines crop_image, but MEDIA_LIBRARY_MODEL "
                "is not configured; the hook is never called.",
            )
        ]

    return []


def login_backend_warnings() -> list[tuple[str, str]]:
    """
    An empty LOGIN_BACKENDS setting, as (check id, message) pairs.
    Without a login backend, nobody can sign in to the studio.
    """
    if not cs_settings.LOGIN_BACKENDS:
        return [
            (
                "content_studio.W009",
                "LOGIN_BACKENDS is empty; no login backend is configured, "
                "so nobody can sign in to Content Studio.",
            )
        ]

    return []


def presence_cache_backend() -> str:
    """
    The dotted path of the cache backend presence is stored in, or an
    empty string when presence is off or the alias is not configured.
    """
    if not cs_settings.PRESENCE:
        return ""

    config = getattr(settings, "CACHES", {}).get(cs_settings.PRESENCE_CACHE)

    return (config or {}).get("BACKEND", "")


def presence_errors() -> list[tuple[str, str]]:
    """
    A PRESENCE_CACHE that names no configured cache, as (check id,
    message) pairs: every heartbeat would fail.
    """
    if not cs_settings.PRESENCE:
        return []

    alias = cs_settings.PRESENCE_CACHE

    if not isinstance(alias, str) or alias not in getattr(settings, "CACHES", {}):
        return [
            (
                "content_studio.E023",
                f"PRESENCE_CACHE is {alias!r}, which is not a cache in the "
                "CACHES setting; name a configured cache or set PRESENCE to "
                "False.",
            )
        ]

    return []


def devtools_errors() -> list[tuple[str, str]]:
    """
    A DEVTOOLS that is not True or False, or a DEVTOOLS_LOGGERS that is
    not a list of logger names, as (check id, message) pairs.
    """
    errors = []
    enabled = cs_settings.DEVTOOLS
    loggers = cs_settings.DEVTOOLS_LOGGERS

    if not isinstance(enabled, bool):
        errors.append(
            (
                "content_studio.E049",
                f"DEVTOOLS is {enabled!r}; set it to True (developer tools "
                "while DEBUG is on) or False.",
            )
        )

    if not isinstance(loggers, (list, tuple)) or not all(
        isinstance(name, str) and name for name in loggers
    ):
        errors.append(
            (
                "content_studio.E049",
                f"DEVTOOLS_LOGGERS is {loggers!r}; set it to a list of logger "
                'names, such as ["myproject"].',
            )
        )

    return errors


def thumbnail_errors() -> list[tuple[str, str]]:
    """
    A THUMBNAIL_CACHE that names no configured cache while thumbnails
    are on, as (check id, message) pairs: every thumbnail would fail.
    """
    if not cs_settings.THUMBNAIL_FOLDER:
        return []

    alias = cs_settings.THUMBNAIL_CACHE

    if not isinstance(alias, str) or alias not in getattr(settings, "CACHES", {}):
        return [
            (
                "content_studio.E027",
                f"THUMBNAIL_CACHE is {alias!r}, which is not a cache in the "
                "CACHES setting; name a configured cache or set "
                "THUMBNAIL_FOLDER to None.",
            )
        ]

    return []


def image_size_errors() -> list[tuple[str, str]]:
    """
    IMAGE_SIZES entries that cannot be made, as (check id, message)
    pairs: such a size is left out.
    """
    from .media_library.sizes import image_sizes_errors

    return [("content_studio.E033", error) for error in image_sizes_errors()]


def image_size_warnings() -> list[tuple[str, str]]:
    """
    IMAGE_SIZES set while sizes cannot be made, as (check id, message)
    pairs: every size is then the image's own file.
    """
    from .media_library.metadata import get_metadata_attr
    from .media_library.sizes import get_size_specs, pillow_available

    if not cs_settings.IMAGE_SIZES or not get_size_specs():
        return []

    reasons = []

    if not cs_settings.IMAGE_SIZE_FOLDER:
        reasons.append("IMAGE_SIZE_FOLDER is not set")

    if not cs_settings.MEDIA_LIBRARY_MODEL:
        reasons.append("MEDIA_LIBRARY_MODEL is not set")
    elif not get_metadata_attr():
        reasons.append(
            "the media model has no JSONField named by MEDIA_METADATA_ATTR "
            "to record them in"
        )

    if not pillow_available():
        reasons.append("Pillow is not installed (django-content-studio[images])")

    if not reasons:
        return []

    return [
        (
            "content_studio.W022",
            f"IMAGE_SIZES is set but no image sizes are made: {'; '.join(reasons)}.",
        )
    ]


def presence_warnings() -> list[tuple[str, str]]:
    """
    Presence stored in the dummy cache, as (check id, message) pairs:
    the cache keeps nothing, so nobody is ever shown.
    """
    if presence_cache_backend() == "django.core.cache.backends.dummy.DummyCache":
        return [
            (
                "content_studio.W016",
                "Presence is stored in a DummyCache, which keeps nothing, so "
                "the admin never shows who has an object open; configure "
                "another cache in PRESENCE_CACHE or set PRESENCE to False.",
            )
        ]

    return []


@checks.register(checks.Tags.caches, deploy=True)
def check_presence_deployment(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """
    Presence in a per-process cache, a deployment check: with several
    worker processes or servers, each keeps its own entries and editors
    only see the users served by the same process. The development
    server runs one process, where the default local-memory cache works.
    """
    backend = presence_cache_backend()

    if backend == "django.core.cache.backends.locmem.LocMemCache":
        return [
            checks.Warning(
                "Presence is stored in a LocMemCache, which each process "
                "keeps for itself; with several worker processes or servers, "
                "editors only see the users served by the same process.",
                hint="Configure a shared cache (Redis, Memcached or the "
                "database cache) in PRESENCE_CACHE, or set PRESENCE to False.",
                obj=cs_settings.ADMIN_SITE.__class__.__name__,
                id="content_studio.W017",
            )
        ]

    return []


def password_reset_mail_in_request() -> bool:
    """
    Whether password reset emails are sent during the request: by an
    ImmediateBackend (the default without a TASKS setting), or in place
    without a tasks framework (Django 5.2 without django-tasks).
    """
    from .contrib.password_reset import tasks

    task = tasks.send_reset_code

    if isinstance(task, tasks._SynchronousTask):
        return True

    try:
        backend = task.get_backend()
    except Exception:
        # A misconfigured TASKS setting is reported by Django's own checks.
        return False

    immediate = []
    for module in (
        "django.tasks.backends.immediate",
        "django_tasks.backends.immediate",
    ):
        try:
            immediate.append(import_module(module).ImmediateBackend)
        except ImportError:
            pass

    return isinstance(backend, tuple(immediate))


@checks.register(checks.Tags.security, deploy=True)
def check_password_reset_deployment(
    app_configs=None, **kwargs
) -> list[checks.CheckMessage]:
    """
    Password reset emails sent during the request, a deployment check:
    an email is only sent for an account, so the response time reveals
    which addresses have one.
    """
    if not apps.is_installed("content_studio.contrib.password_reset"):
        return []

    if password_reset_mail_in_request():
        return [
            checks.Warning(
                "Password reset emails are sent during the request, so its "
                "duration reveals which email addresses have an account.",
                hint="Configure a task backend that runs Django tasks in a "
                "worker (the TASKS setting).",
                id="content_studio.W018",
            )
        ]

    return []


def two_factor_errors() -> list[tuple[str, str]]:
    """
    A malformed two-factor setting, as (check id, message) pairs:
    TWO_FACTOR_REQUIRED is None, "superusers" or "all", and needs the
    two-factor app; TWO_FACTOR_THROTTLE_RATE is like "10/hour".
    """
    from .login import TWO_FACTOR_APP, TWO_FACTOR_REQUIRED_VALUES

    errors = []
    required = cs_settings.TWO_FACTOR_REQUIRED

    if required is not None and required not in TWO_FACTOR_REQUIRED_VALUES:
        errors.append(
            (
                "content_studio.E044",
                'TWO_FACTOR_REQUIRED must be None, "superusers" or "all", '
                f"not {required!r}.",
            )
        )
    elif required and not apps.is_installed(TWO_FACTOR_APP):
        errors.append(
            (
                "content_studio.E044",
                f"TWO_FACTOR_REQUIRED is {required!r}, but the two-factor app "
                f"is not installed: add {TWO_FACTOR_APP!r} to INSTALLED_APPS.",
            )
        )

    rate = cs_settings.TWO_FACTOR_THROTTLE_RATE

    if rate is not None:
        try:
            parse_rate(rate)
        except Exception:
            errors.append(
                (
                    "content_studio.E044",
                    "TWO_FACTOR_THROTTLE_RATE must be a rate such as "
                    f'"10/hour" or None, not {rate!r}.',
                )
            )

    return errors


@checks.register(checks.Tags.security)
def check_two_factor(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    return [
        checks.Error(message, id=check_id) for check_id, message in two_factor_errors()
    ]


def login_throttle_errors() -> list[str]:
    """
    Login rate limits that cannot be read, which would fail every login:
    LOGIN_THROTTLE_RATE and LOGIN_ACCOUNT_THROTTLE_RATE are like
    "10/min" or None.
    """
    errors = []

    for name in ("LOGIN_THROTTLE_RATE", "LOGIN_ACCOUNT_THROTTLE_RATE"):
        rate = getattr(cs_settings, name)

        if rate is None:
            continue

        try:
            parse_rate(rate)
        except Exception:
            errors.append(
                f'{name} must be a rate such as "10/min" or None, not {rate!r}.'
            )

    return errors


def translation_errors(studio) -> list[tuple[str, str]]:
    """
    A malformed `translations` (E055): a list of field names or a
    Translations naming fields the adapter knows, languages among the
    content languages, required languages among them and a known
    adapter.
    """
    from .translations import (
        ADAPTERS,
        TranslationAdapter,
        Translations,
        get_content_languages,
        get_studio_translations,
        resolve_adapter,
    )

    value = getattr(studio, "translations", None)
    name = config_name(studio)
    model = getattr(studio, "model", None)

    if value is None or value is False or model is None:
        return []

    if not isinstance(value, (list, tuple, Translations)) or (
        isinstance(value, (list, tuple))
        and not all(isinstance(entry, str) for entry in value)
    ):
        return [
            (
                "content_studio.E055",
                f"{name}.translations must be a list of field names or a "
                "Translations.",
            )
        ]

    config = get_studio_translations(studio)

    if config is None:
        return []

    adapter = config.adapter

    if isinstance(adapter, str) and adapter not in ADAPTERS:
        return [
            (
                "content_studio.E055",
                f"{name}.translations has an unknown adapter {adapter!r}; use "
                + ", ".join(repr(key) for key in ADAPTERS)
                + " or a TranslationAdapter subclass.",
            )
        ]

    if not isinstance(adapter, (str, type(None))) and not (
        isinstance(adapter, type) and issubclass(adapter, TranslationAdapter)
    ):
        return [
            (
                "content_studio.E055",
                f"{name}.translations adapter must be a TranslationAdapter "
                "subclass.",
            )
        ]

    errors = []
    resolved = resolve_adapter(model, config)

    for field in config.fields or []:
        if resolved.model_field(field) is None:
            errors.append(
                (
                    "content_studio.E055",
                    f"{name}.translations names {field!r}, which is not a "
                    f"field of {model._meta.label}.",
                )
            )

    codes = [code for code, _ in get_content_languages()]

    for code in config.languages or []:
        if code not in codes:
            errors.append(
                (
                    "content_studio.E055",
                    f"{name}.translations has language {code!r}, which is "
                    "not in CONTENT_LANGUAGES (or LANGUAGES).",
                )
            )

    languages = config.languages or codes

    for code in config.required or []:
        if code not in languages:
            errors.append(
                (
                    "content_studio.E055",
                    f"{name}.translations requires language {code!r}, which "
                    "is not one of its languages.",
                )
            )

    return errors


def translation_warnings(studio) -> list[tuple[str, str]]:
    """
    A translated field without a column for one of the languages a
    studio names, or CONTENT_LANGUAGES sets (W030): that language is
    not offered for the field.
    """
    from .translations import build_translation_config, get_studio_translations

    explicit = get_studio_translations(studio)

    if explicit is None or (
        explicit.languages is None and not cs_settings.CONTENT_LANGUAGES
    ):
        return []

    try:
        config = build_translation_config(studio)
    except Exception:
        # Reported by E055.
        return []

    if config is None:
        return []

    warnings = []
    wanted = explicit.languages or [
        code for code, _ in cs_settings.CONTENT_LANGUAGES or []
    ]
    columns = config.columns()

    for field, per_language in columns.items():
        missing = [code for code in wanted if code not in per_language]

        if missing:
            warnings.append(
                (
                    "content_studio.W030",
                    f"{config_name(studio)}.translations: {field!r} has no "
                    f"column for {', '.join(missing)}, so editors cannot "
                    "translate it into "
                    + ("that language." if len(missing) == 1 else "those languages."),
                )
            )

    return warnings


@checks.register(checks.Tags.security)
def check_login_throttles(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    return [
        checks.Error(message, id="content_studio.E053")
        for message in login_throttle_errors()
    ]


def profile_field_errors(site) -> list[tuple[str, str]]:
    """
    A malformed profile_fields, as (check id, message) pairs: entries are
    field names or Field objects naming a field of the user model,
    without when=; the password, the username and the fields deciding
    what a user may do can only be shown read-only.
    """
    from .profile import protected_field_names

    configured = getattr(site, "profile_fields", None)

    if configured is None:
        return []

    if not isinstance(configured, (list, tuple)):
        return [
            (
                "content_studio.E041",
                "profile_fields must be a list of field names or Field "
                f"objects, not {type(configured).__name__}.",
            )
        ]

    user_model = get_user_model()
    protected = protected_field_names(user_model)
    errors = []

    for entry in configured:
        if isinstance(entry, str):
            name, readonly, when = entry, False, None
        elif isinstance(entry, Field):
            name, readonly, when = entry.name, entry.readonly, entry.when
        else:
            errors.append(
                (
                    "content_studio.E041",
                    f"profile_fields entry {entry!r} is not a field name or a "
                    "Field.",
                )
            )
            continue

        try:
            model_field = user_model._meta.get_field(name)
        except FieldDoesNotExist:
            errors.append(
                (
                    "content_studio.E041",
                    f"profile_fields names {name!r}, which is not a field of "
                    f"{user_model._meta.label}.",
                )
            )
            continue

        if name == "password" or getattr(model_field, "attname", "") == "password":
            errors.append(
                (
                    "content_studio.E041",
                    "profile_fields cannot name 'password': the profile page "
                    "changes it in its own dialog.",
                )
            )
        elif name in protected and not readonly:
            errors.append(
                (
                    "content_studio.E041",
                    f"profile_fields names {name!r}, which editors may not "
                    f"change on their own profile; use Field({name!r}, "
                    "readonly=True) to show it.",
                )
            )

        if when is not None:
            errors.append(
                (
                    "content_studio.E041",
                    f"profile_fields entry {name!r} has when=, which the "
                    "profile page does not support.",
                )
            )

    return errors


def map_setting_errors() -> list[tuple[str, str]]:
    """
    Malformed map and embed settings, as (check id, message) pairs: the
    tile URL must be a template with {z}, {x} and {y}, the attribution
    a string, the geocoder None or an http(s) URL, and the oEmbed
    providers None or a list of provider dicts.
    """
    errors = []
    tile_url = cs_settings.MAP_TILE_URL

    if not isinstance(tile_url, str) or not all(
        part in tile_url for part in ("{z}", "{x}", "{y}")
    ):
        errors.append(
            (
                "content_studio.E034",
                "MAP_TILE_URL must be a tile URL template with {z}, {x} and "
                "{y}, like 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'.",
            )
        )

    if not isinstance(cs_settings.MAP_TILE_ATTRIBUTION, str):
        errors.append(
            (
                "content_studio.E034",
                "MAP_TILE_ATTRIBUTION must be a string, like '&copy; "
                "OpenStreetMap contributors'.",
            )
        )

    geocoder = cs_settings.MAP_GEOCODER_URL

    if geocoder is not None and not _is_absolute_url(geocoder):
        errors.append(
            (
                "content_studio.E034",
                "MAP_GEOCODER_URL must be None or an http(s) URL, like "
                "'https://nominatim.openstreetmap.org/search'.",
            )
        )

    providers = cs_settings.OEMBED_PROVIDERS

    if providers is not None:
        if isinstance(providers, (str, dict)) or not isinstance(
            providers, (list, tuple)
        ):
            errors.append(
                (
                    "content_studio.E034",
                    "OEMBED_PROVIDERS must be None or a list of providers, "
                    "each {'name': ..., 'endpoint': ..., 'patterns': [...]}.",
                )
            )
        else:
            for provider in providers:
                error = _oembed_provider_error(provider)

                if error:
                    errors.append(("content_studio.E034", error))

    return errors


def _oembed_provider_error(provider):
    import re

    if not isinstance(provider, dict):
        return f"OEMBED_PROVIDERS entry {provider!r} is not a dict."

    name = provider.get("name")

    if not isinstance(name, str) or not name:
        return f"OEMBED_PROVIDERS entry {provider!r} needs a name."

    if not _is_absolute_url(provider.get("endpoint")):
        return f"OEMBED_PROVIDERS provider {name!r} needs an http(s) endpoint."

    patterns = provider.get("patterns")

    if (
        isinstance(patterns, str)
        or not isinstance(patterns, (list, tuple))
        or not patterns
    ):
        return (
            f"OEMBED_PROVIDERS provider {name!r} needs a list of URL "
            "patterns (regular expressions)."
        )

    for pattern in patterns:
        try:
            re.compile(pattern)
        except (re.error, TypeError):
            return (
                f"OEMBED_PROVIDERS provider {name!r} has an invalid pattern "
                f"{pattern!r}; patterns are regular expressions."
            )

    return None


NUMBER_FIELDS = (models.FloatField, models.DecimalField)


def rich_text_widget_warnings(studio) -> list[tuple[str, str]]:
    """
    RichTextWidget options that cannot work, as (check id, message)
    pairs: the image feature without a media library, link_models that
    are not registered or have no URL, and image_sizes that are not in
    IMAGE_SIZES.
    """
    from .admin import is_linkable
    from .media_library.sizes import get_size_specs
    from .rich_text import ORIGINAL_SIZE

    model = getattr(studio, "model", None)

    if model is None:
        return []

    site = cs_settings.ADMIN_SITE
    registry = getattr(site, "_registry", {})
    studios = {m._meta.label_lower: s for m, s in registry.items()}
    sizes = set(get_size_specs()) | {ORIGINAL_SIZE}
    fields = {field.name: field for field in model._meta.get_fields()}
    warnings = []

    def warn(message):
        warnings.append(
            ("content_studio.W025", f"{studio.__class__.__name__}: {message}")
        )

    for field in iter_edit_fields(studio):
        model_field = fields.get(field.name)
        widget = field.widget or getattr(model_field, "widget_class", None)

        if model_field is None or not is_kind(widget, widgets.RichTextWidget):
            continue

        widget = as_instance(widget)

        if (
            widget.features is not None
            and "image" in widget.features
            and cs_settings.MEDIA_LIBRARY_MODEL is None
        ):
            warn(
                f"RichTextWidget on {field.name!r} has the image feature, but "
                "MEDIA_LIBRARY_MODEL is not set, so it has no images to insert."
            )

        for label in widget.link_models or []:
            linked = studios.get(label)

            if linked is None:
                warn(
                    f"RichTextWidget on {field.name!r} links to {label!r}, "
                    "which is not a registered model."
                )
            elif not is_linkable(linked):
                warn(
                    f"RichTextWidget on {field.name!r} links to {label!r}, "
                    "whose objects have no URL: give the model "
                    "get_absolute_url() or its studio get_link_url()."
                )
            elif not linked.search_fields:
                warn(
                    f"RichTextWidget on {field.name!r} links to {label!r}, "
                    "whose studio has no search_fields, so its objects "
                    "cannot be found in the link dialog."
                )

        for name in widget.image_sizes or []:
            if name not in sizes:
                warn(
                    f"RichTextWidget on {field.name!r} offers the image size "
                    f"{name!r}, which is not in IMAGE_SIZES."
                )

    return warnings


def map_widget_errors(studio) -> list[tuple[str, str]]:
    """
    MapWidget on a field it cannot edit, as (check id, message) pairs.
    The widget stores {"lat", "lng"} in a JSONField, or the latitude in
    a FloatField or DecimalField and the longitude in the number field
    lng_field names.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    fields = {field.name: field for field in model._meta.get_fields()}
    errors = []

    def error(message):
        errors.append(
            (
                "content_studio.E035",
                f"{studio.__class__.__name__}: {message}",
            )
        )

    for field in iter_edit_fields(studio):
        model_field = fields.get(field.name)
        widget = field.widget or getattr(model_field, "widget_class", None)

        if model_field is None or not is_kind(widget, widgets.MapWidget):
            continue

        lng_field = getattr(as_instance(widget), "lng_field", None)

        if isinstance(model_field, models.JSONField):
            if lng_field is not None:
                error(
                    f"MapWidget on {field.name!r} stores the location in the "
                    "JSONField; lng_field is for a latitude number field."
                )
        elif isinstance(model_field, NUMBER_FIELDS):
            lng_model_field = fields.get(lng_field) if lng_field else None

            if lng_field is None:
                error(
                    f"MapWidget on the number field {field.name!r} needs "
                    "lng_field, the field holding the longitude."
                )
            elif lng_field == field.name or not isinstance(
                lng_model_field, NUMBER_FIELDS
            ):
                error(
                    f"MapWidget on {field.name!r} has lng_field {lng_field!r}, "
                    f"which is not a FloatField or DecimalField on "
                    f"{model._meta.label_lower}."
                )
        else:
            error(
                f"MapWidget on {field.name!r} edits a JSONField, or a "
                "FloatField or DecimalField with lng_field; the field on "
                f"{model._meta.label_lower} is neither."
            )

    return errors


def iter_edit_components(studio):
    """
    Yield the Component objects declared in a model studio's edit_main
    and edit_sidebar, across form sets and groups.
    """
    all_fields = list(getattr(studio, "edit_main", None) or []) + list(
        getattr(studio, "edit_sidebar", None) or []
    )

    for entry in flatten(
        [
            entry.get_fields() if hasattr(entry, "get_fields") else [entry]
            for entry in all_fields
        ]
    ):
        if isinstance(entry, Component):
            yield entry


def seo_preview_errors(studio) -> list[tuple[str, str]]:
    """
    SEOPreview components naming fields the model does not have, as
    (check id, message) pairs: the preview reads the title, description
    and path from the form's values, so an unknown name stays empty.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    errors = []
    field_names = model_field_names(model)

    for component in iter_edit_components(studio):
        if not isinstance(component, SEOPreview):
            continue

        for option in ("title_field", "description_field", "path_field"):
            name = getattr(component, option)

            if name is not None and name not in field_names:
                errors.append(
                    (
                        "content_studio.E036",
                        f"{studio.__class__.__name__}: SEOPreview {option} "
                        f"{name!r} does not exist on {model._meta.label_lower}.",
                    )
                )

    return errors


def iter_whens(studio):
    """
    Yield (description, when) for every when= on a studio's edit page:
    header components, tabs, form sets, fields and components.
    """

    def describe(entry) -> str:
        if isinstance(entry, Field):
            return f"Field({entry.name!r})"
        if isinstance(entry, FormSet):
            return f"FormSet({entry.title!r})"
        if isinstance(entry, FormSetGroup):
            return f"FormSetGroup({entry.label!r})"
        return entry.__class__.__name__

    def visit(entry):
        when = getattr(entry, "when", None)

        if isinstance(entry, (Field, FormSet, FormSetGroup, Component)) and (
            when is not None
        ):
            yield describe(entry), when

        if isinstance(entry, FormSetGroup):
            for form_set in entry.formsets:
                yield from visit(form_set)

        if isinstance(entry, (FormSet, FieldLayout)):
            for field in entry.fields:
                yield from visit(field)

    header = getattr(studio, "edit_header", None)
    entries = (
        (list(header) if isinstance(header, (list, tuple)) else [])
        + list(getattr(studio, "edit_main", None) or [])
        + list(getattr(studio, "edit_sidebar", None) or [])
    )

    for entry in entries:
        yield from visit(entry)


def condition_errors(studio) -> list[tuple[str, str]]:
    """
    Conditions (when=) that read fields the edit page's form does not
    hold, as (check id, message) pairs: fields the model does not have,
    and excluded or write-only fields, whose values never reach the
    admin. Either way the condition reads an empty value.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    errors = []
    field_names = model_field_names(model)
    hidden = set(getattr(studio, "exclude", None) or []) | get_write_only_field_names(
        studio, model
    )

    for owner, when in iter_whens(studio):
        for name in referenced_fields(when):
            if name not in field_names:
                errors.append(
                    (
                        "content_studio.E040",
                        f"{config_name(studio)}: the condition of {owner} "
                        f"reads {name!r}, which is not a field of "
                        f"{model._meta.label_lower}.",
                    )
                )
            elif name in hidden:
                errors.append(
                    (
                        "content_studio.E040",
                        f"{config_name(studio)}: the condition of {owner} "
                        f"reads {name!r}, which is excluded or write-only, so "
                        "its value never reaches the admin.",
                    )
                )

    return errors


def condition_warnings(studio) -> list[tuple[str, str]]:
    """
    Required model fields that only show under a condition, as (check
    id, message) pairs: a hidden field is not saved, so creating an
    object while it is hidden fails.
    """
    model = getattr(studio, "model", None)

    if model is None:
        return []

    ignored = ignored_edit_field_names(model)
    required = {
        field.name
        for field in model._meta.get_fields()
        if is_required_model_field(field) and field.name not in ignored
    }
    warnings = []

    for name, placements in get_field_placements(studio, None).items():
        if name in required and placements and all(placements):
            warnings.append(
                (
                    "content_studio.W024",
                    f"{config_name(studio)}: the required field {name!r} only "
                    "shows under a condition, and a hidden field is not "
                    "saved, so creating an object while it is hidden fails. "
                    "Give the model field a default, make it nullable or "
                    "blank, or show it always.",
                )
            )

    return warnings


@checks.register()
def check_content_studio(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    site = cs_settings.ADMIN_SITE

    messages = []

    for model, studio in site._registry.items():
        obj = f"{studio.__class__.__name__} ({model._meta.label_lower})"

        for check_id, error in list_config_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in table_column_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in bulk_action_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in action_form_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in soft_delete_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in reorder_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in publishing_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in review_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in table_edit_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in edit_form_config_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in list_query_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in list_filter_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in inline_fk_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in duplicate_inline_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in tenant_field_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in readonly_fields_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in prepopulated_fields_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in edit_header_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in edit_width_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in map_widget_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in seo_preview_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in condition_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in duplication_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in view_on_site_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in preview_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in export_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        for check_id, error in import_errors(studio):
            messages.append(checks.Error(error, obj=obj, id=check_id))

        translations_valid = True

        for check_id, error in translation_errors(studio):
            translations_valid = False
            messages.append(checks.Error(error, obj=obj, id=check_id))

        if translations_valid:
            for check_id, warning in translation_warnings(studio):
                messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in edit_field_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in readonly_required_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in choice_widget_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in cover_image_widget_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in rich_text_widget_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in sortable_by_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in reorder_ordering_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in list_filter_entry_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in list_display_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in table_edit_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in duplication_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in recover_changes_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in export_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in import_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

        for check_id, warning in condition_warnings(studio):
            messages.append(checks.Warning(warning, obj=obj, id=check_id))

    for check_id, error in duplicate_id_errors(site):
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in dashboard_page_errors(site):
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in mapping_errors(site):
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in focal_point_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in media_metadata_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in media_properties_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in media_upload_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in profile_field_errors(site):
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in map_setting_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in webhook_setting_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in notification_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in status_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in [*backup_errors(), *backup_storage_errors()]:
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, warning in backup_warnings():
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in preview_middleware_warnings():
        messages.append(checks.Warning(warning, id=check_id))

    for check_id, error in presence_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in devtools_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in thumbnail_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, error in image_size_errors():
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, warning in image_size_warnings():
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in dashboard_widget_warnings(site):
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in task_adapter_warnings(site):
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, error in analytics_errors(site):
        messages.append(checks.Error(error, obj=site.__class__.__name__, id=check_id))

    for check_id, warning in analytics_warnings(site):
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in model_group_warnings(site):
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in media_library_warnings():
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in crop_hook_warnings():
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in login_backend_warnings():
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    for check_id, warning in presence_warnings():
        messages.append(
            checks.Warning(warning, obj=site.__class__.__name__, id=check_id)
        )

    return messages
