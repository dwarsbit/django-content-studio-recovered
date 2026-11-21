"""
Translated content: fields written in every content language.

A studio names its translated fields (`translations = ["title", ...]`).
The first content language is kept in the field itself, every other one
in a column named <field>_<code> (the layout of django-modeltranslation,
django-translated-fields and hand-made columns).

WIP spike for the mockups: the columns adapter only.
"""

from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .filters import ListFilter

from .settings import cs_settings


def get_content_languages():
    languages = cs_settings.CONTENT_LANGUAGES or settings.LANGUAGES

    return [(code, str(name)) for code, name in languages]


def column_name(field, code, default):
    return field if code == default else f"{field}_{code.replace('-', '_')}"


def get_translation_columns(studio):
    """
    {field: {code: column}} for the studio's translated fields, or {}.
    """
    names = list(getattr(studio, "translations", None) or [])

    if not names:
        return {}

    languages = get_content_languages()
    default = languages[0][0]
    model_fields = {field.name for field in studio.model._meta.get_fields()}

    return {
        name: {
            code: column_name(name, code, default)
            for code, _ in languages
            if column_name(name, code, default) in model_fields
        }
        for name in names
    }


def serialize_translations(studio):
    columns = get_translation_columns(studio)

    if not columns:
        return None

    languages = get_content_languages()

    return {
        "languages": [{"code": code, "name": name} for code, name in languages],
        "default": languages[0][0],
        "required": [languages[0][0]],
        "fields": columns,
    }


def get_language_states(studio, obj):
    """
    {code: number of translated fields left empty} for an object.
    """
    columns = get_translation_columns(studio)
    states = {}

    for code, _ in get_content_languages():
        states[code] = sum(
            1
            for per_language in columns.values()
            if code in per_language
            and not getattr(obj, per_language[code], None)
        )

    return states


def missing_q(studio, code):
    """A Q matching objects with a translated field empty in a language."""
    query = Q()

    for per_language in get_translation_columns(studio).values():
        if code in per_language:
            column = per_language[code]
            query |= Q(**{column: ""}) | Q(**{f"{column}__isnull": True})

    return query



class MissingTranslationFilter(ListFilter):
    """The list filter "Missing translation": objects with a translated
    field left empty in the picked languages."""

    title = _("Missing translation")
    parameter_name = "missing_translation"
    multiple = True

    def get_options(self, request):
        return get_content_languages()[1:]

    def queryset(self, request, queryset, value):
        query = Q()
        for code in value:
            query |= missing_q(self.studio, code)
        return queryset.filter(query)
