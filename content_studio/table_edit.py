"""
Inline editing of the table view (ModelStudio.table_edit, alias
list_editable): which columns a request may edit in place, the kinds of
model fields a cell can edit, and the save of one cell, which goes
through the same update path as the edit page.
"""

from typing import Any, Optional

from django.db import models
from django.http import HttpRequest

# The model fields a table cell edits: text and number inputs, switches,
# selects (any field with choices), date and time pickers and foreign
# key pickers.
CELL_FIELDS = (
    models.BooleanField,
    models.CharField,
    models.TextField,
    models.IntegerField,
    models.DecimalField,
    models.FloatField,
    models.DateField,
    models.TimeField,
    models.ForeignKey,
)


def declared_table_edit(studio) -> list[str]:
    """
    The names a studio asks to edit in place: table_edit, or the Django
    admin's list_editable when table_edit is not set.
    """
    from .admin import declares

    if declares(studio, "table_edit"):
        return list(getattr(studio, "table_edit", None) or [])

    alias = getattr(studio, "list_editable", None)

    if isinstance(alias, (list, tuple)):
        return list(alias)

    return []


def link_column(studio) -> Optional[str]:
    """
    The table's first column, which opens the object, so it is never
    edited in place (like the Django admin's list_editable).
    """
    from .admin import get_table_display_columns

    columns = get_table_display_columns(studio)

    return columns[0].field if columns else None


def cell_field_error(studio, name: str) -> Optional[str]:
    """Why a table cell cannot edit the named field, or None."""
    from .publishing import get_publishing

    try:
        field = studio.model._meta.get_field(name)
    except Exception:
        return "is not a field of the model"

    if field.many_to_many:
        return "is a many-to-many field, which a table cell cannot edit"

    if field.primary_key or (field.concrete and not field.editable):
        return "is not editable"

    if not field.concrete or field.auto_created:
        return "is a reverse relation, which a table cell cannot edit"

    publishing = get_publishing(studio)

    if publishing is not None and name in (
        publishing.published_at,
        publishing.unpublish_at,
        publishing.status,
    ):
        return (
            "is set by publishing; the Status column and the Publish actions "
            "change it"
        )

    # Content Studio's own content fields (HTMLField, BlockField, ...)
    # bring a widget a cell does not have.
    if hasattr(field, "widget_class"):
        return "has a widget a table cell cannot show"

    if not isinstance(field, CELL_FIELDS):
        return f"is a {field.__class__.__name__}, which a table cell cannot edit"

    return None


def get_default_table_edit(studio, request: HttpRequest) -> list[str]:
    """
    ModelStudio.get_table_edit's default: the declared names the editor
    can write, which leaves out the first column (it opens the object),
    read-only fields, fields the edit page does not write and everything
    for editors without change permission.
    """
    from .admin import get_form_field_names, get_readonly_field_names

    names = declared_table_edit(studio)

    if not names or not studio.has_change_permission(request):
        return []

    form_names = get_form_field_names(studio, request)
    readonly = get_readonly_field_names(studio, request)
    link = link_column(studio)

    return [
        name
        for name in names
        if name != link
        and name in form_names
        and name not in readonly
        and cell_field_error(studio, name) is None
    ]


def get_cell_keys(studio, request: HttpRequest) -> dict[str, str]:
    """
    {data key: field name} of the cells the editor may save: each
    editable name, and each language's column of a translated one.
    """
    from .translations import build_translation_config

    names = studio.get_table_edit(request)
    keys = {name: name for name in names}
    config = build_translation_config(studio)

    if config is not None:
        for name, per_language in config.columns().items():
            if name in keys:
                keys.update({column: name for column in per_language.values()})

    return keys


def comparable(value: Any) -> Any:
    """A representation's value as the conflict check compares it."""
    if isinstance(value, dict) and "id" in value:
        return str(value["id"])

    if value is None:
        return None

    return str(value)
