"""
Translated content: fields written in more than one content language.

A studio names its translated fields with `translations`: a list of
field names, or a `Translations` object for the languages, the
languages that must be complete and the adapter. Models registered with
django-modeltranslation or built on django-parler's TranslatableModel
are detected without it.

Content Studio stores nothing itself. An adapter maps each translated
field and language to where the value lives:

- ColumnsAdapter: one column per language, <field>_<code> (such as
  title_nl), with the default language in the field itself. Plain
  Django columns and django-translated-fields use this layout.
- ModelTranslationAdapter: django-modeltranslation's columns; every
  language, the default one too, has its own column.
- ParlerAdapter: django-parler's translations table. Its values travel
  to the editor as <field>__<code>, which no model field can be named.

The content languages (CONTENT_LANGUAGES) are not the admin's interface
languages (languages.py): an editor working in Dutch can write German.
"""

from typing import Any, Optional, Sequence, Union

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .filters import ListFilter
from .settings import cs_settings

__all__ = [
    "ColumnsAdapter",
    "MissingTranslationFilter",
    "ModelTranslationAdapter",
    "ParlerAdapter",
    "TranslationAdapter",
    "Translations",
]

Language = tuple[str, str]


def get_content_languages() -> list[Language]:
    """
    The content languages as (code, name) pairs, the default first:
    CONTENT_LANGUAGES, else settings.LANGUAGES with LANGUAGE_CODE's
    language first.
    """
    configured = cs_settings.CONTENT_LANGUAGES

    if configured:
        return [(code, str(name)) for code, name in configured]

    languages = [(code, str(name)) for code, name in settings.LANGUAGES]
    default = default_language_code([code for code, _ in languages])

    return sorted(languages, key=lambda language: language[0] != default)


def default_language_code(codes: Sequence[str]) -> Optional[str]:
    """LANGUAGE_CODE, or its base language, when it is one of the codes."""
    code = (settings.LANGUAGE_CODE or "").lower()

    for candidate in (code, code.split("-")[0]):
        for available in codes:
            if available.lower() == candidate:
                return available

    return codes[0] if codes else None


def column_suffix(code: str) -> str:
    """A language code as a column suffix: pt-br becomes pt_br."""
    return code.replace("-", "_").lower()


class Translations:
    """
    A studio's translated fields:

        class ArticleStudio(ModelStudio):
            translations = Translations(
                fields=["title", "slug", "body"],
                languages=["en", "nl", "de"],
                required=["en"],
            )

    `fields` defaults to every translated field the adapter knows (the
    modeltranslation or parler registration). `languages` is a subset
    of CONTENT_LANGUAGES, in that order; the first is the default
    language. `required` lists the languages that must be complete to
    save, the default language by default. `adapter` is "columns",
    "modeltranslation", "parler" or a TranslationAdapter subclass;
    by default it follows the model.
    """

    def __init__(
        self,
        fields: Optional[Sequence[str]] = None,
        *,
        languages: Optional[Sequence[str]] = None,
        required: Optional[Sequence[str]] = None,
        adapter: Union[str, type["TranslationAdapter"], None] = None,
    ):
        self.fields = list(fields) if fields is not None else None
        self.languages = list(languages) if languages is not None else None
        self.required = list(required) if required is not None else None
        self.adapter = adapter


class TranslationAdapter:
    """
    Where a model keeps its translations. Subclass it for another
    storage and pass the class as `Translations(adapter=...)`.
    """

    # Whether the editor's names (columns()) are model fields. Virtual
    # names are read and written through get_value() and set_value().
    virtual = False

    def __init__(self, model: type[models.Model], config: Translations):
        self.model = model
        self.config = config

    @classmethod
    def detect(cls, model) -> bool:
        """Whether this adapter fits the model without being named."""
        return False

    def known_fields(self) -> list[str]:
        """The translated fields, when the studio does not name them."""
        return []

    def fields(self) -> list[str]:
        if self.config.fields is not None:
            return list(self.config.fields)

        return self.known_fields()

    def column(self, field: str, code: str, default: str) -> str:
        """The editor's name of a field in a language."""
        raise NotImplementedError

    def has_column(self, field: str, code: str, default: str) -> bool:
        return True

    def model_field(self, field: str) -> Optional[models.Field]:
        """The model field that describes a translated field."""
        try:
            return self.model._meta.get_field(field)
        except FieldDoesNotExist:
            return None

    def readonly_fields(self) -> list[str]:
        """Model fields the editor must not write (proxies)."""
        return []

    def get_value(self, obj, field: str, code: str) -> Any:
        raise NotImplementedError

    def set_value(self, obj, field: str, code: str, value: Any) -> None:
        raise NotImplementedError

    def empty_q(self, column: str) -> Q:
        return Q(**{f"{column}__isnull": True}) | Q(**{column: ""})

    def missing_q(self, field: str, code: str, default: str) -> Q:
        """Objects whose field is empty in a language."""
        return self.empty_q(self.column(field, code, default))

    def search_lookups(self, field: str, codes: Sequence[str], default: str):
        """The lookups a search on a translated field runs, per language."""
        return [
            self.column(field, code, default)
            for code in codes
            if self.has_column(field, code, default)
        ]


class ColumnsAdapter(TranslationAdapter):
    """title for the default language, title_nl and title_de for others."""

    def column(self, field, code, default):
        return field if code == default else f"{field}_{column_suffix(code)}"

    def has_column(self, field, code, default):
        try:
            self.model._meta.get_field(self.column(field, code, default))
        except FieldDoesNotExist:
            return False

        return True

    def get_value(self, obj, field, code):
        # Columns are read through the editor's names (column()).
        raise NotImplementedError


def modeltranslation_fields(model) -> dict[str, list[str]]:
    """
    {field: [language codes]} of the columns django-modeltranslation
    added to a model. Its TranslationField carries the original field
    and the language, so this needs no import of modeltranslation.
    """
    found: dict[str, list[str]] = {}

    for field in model._meta.get_fields():
        original = getattr(field, "translated_field", None)
        language = getattr(field, "language", None)

        if original is not None and isinstance(language, str):
            found.setdefault(original.name, []).append(language)

    return found


class ModelTranslationAdapter(ColumnsAdapter):
    """django-modeltranslation: title_en, title_nl; title is a proxy."""

    @classmethod
    def detect(cls, model):
        return bool(modeltranslation_fields(model))

    def known_fields(self):
        return list(modeltranslation_fields(self.model))

    def column(self, field, code, default):
        return f"{field}_{column_suffix(code)}"

    def readonly_fields(self):
        # The original field reads and writes the active language's
        # column: written with the admin's language, it would overwrite
        # a translation.
        return self.fields()


class ParlerAdapter(TranslationAdapter):
    """django-parler: the values live in the model's translations table."""

    virtual = True

    @classmethod
    def detect(cls, model):
        return getattr(model, "_parler_meta", None) is not None

    def known_fields(self):
        return list(self.model._parler_meta.get_all_fields())

    def column(self, field, code, default):
        return f"{field}__{column_suffix(code)}"

    def model_field(self, field):
        try:
            meta = self.model._parler_meta._get_extension_by_field(field)
            return meta.model._meta.get_field(field)
        except (KeyError, FieldDoesNotExist):
            return None

    def get_value(self, obj, field, code):
        if obj.pk is None:
            return None

        try:
            translation = obj.get_translation(code)
        except ObjectDoesNotExist:
            return None

        return getattr(translation, field, None)

    def set_value(self, obj, field, code, value):
        translation = obj._get_translated_model(code, auto_create=True)
        setattr(translation, field, value)

    def missing_q(self, field, code, default):
        related = self.model._parler_meta._get_extension_by_field(field).rel_name
        present = Q(**{f"{related}__language_code": code}) & ~(
            Q(**{f"{related}__{field}__isnull": True})
            | Q(**{f"{related}__{field}": ""})
        )

        return ~Q(pk__in=self.model._default_manager.filter(present).values("pk"))

    def search_lookups(self, field, codes, default):
        related = self.model._parler_meta._get_extension_by_field(field).rel_name

        return [f"{related}__{field}"]


def translated_attribute_names(model) -> set[str]:
    """
    The django-parler translated fields of a model: attributes on its
    objects, not model fields, which table_display, search_fields and
    the edit form may still name.
    """
    meta = getattr(model, "_parler_meta", None)

    return set(meta.get_all_fields()) if meta is not None else set()


ADAPTERS: dict[str, type[TranslationAdapter]] = {
    "columns": ColumnsAdapter,
    "modeltranslation": ModelTranslationAdapter,
    "parler": ParlerAdapter,
}


class TranslationConfig:
    """A studio's resolved translations: adapter, languages, columns."""

    def __init__(
        self,
        adapter: TranslationAdapter,
        languages: list[Language],
        required: list[str],
    ):
        self.adapter = adapter
        self.languages = languages
        self.default = languages[0][0]
        self.required = required
        self.fields = adapter.fields()

    @property
    def codes(self) -> list[str]:
        return [code for code, _ in self.languages]

    def language_name(self, code: str) -> str:
        return dict(self.languages).get(code, code)

    def columns(self) -> dict[str, dict[str, str]]:
        """{field: {code: editor name}} for the languages a field has."""
        adapter = self.adapter

        return {
            field: {
                code: adapter.column(field, code, self.default)
                for code in self.codes
                if adapter.has_column(field, code, self.default)
            }
            for field in self.fields
        }

    def column_languages(self) -> dict[str, tuple[str, str]]:
        """{editor name: (field, code)}."""
        return {
            column: (field, code)
            for field, per_language in self.columns().items()
            for code, column in per_language.items()
        }

    def virtual_columns(self) -> dict[str, tuple[str, str]]:
        return self.column_languages() if self.adapter.virtual else {}

    def missing_counts(self, obj) -> dict[str, int]:
        """{code: translated fields left empty} for an object."""
        columns = self.columns()

        return {
            code: sum(
                1
                for field, per_language in columns.items()
                if code in per_language
                and is_empty(self.adapter_value(obj, field, code))
            )
            for code in self.codes
        }

    def adapter_value(self, obj, field, code):
        if self.adapter.virtual:
            return self.adapter.get_value(obj, field, code)

        return getattr(obj, self.adapter.column(field, code, self.default), None)

    def missing_q(self, code: str) -> Q:
        query = Q()

        for field, per_language in self.columns().items():
            if code in per_language:
                query |= self.adapter.missing_q(field, code, self.default)

        return query

    def serialize(self) -> dict[str, Any]:
        return {
            "languages": [
                {"code": code, "name": name} for code, name in self.languages
            ],
            "default": self.default,
            "required": self.required,
            "fields": self.columns(),
        }


def is_empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def get_studio_translations(studio) -> Optional[Translations]:
    """A studio's `translations` as a Translations, or None."""
    value = getattr(studio, "translations", None)

    if value is False:
        return None

    if isinstance(value, Translations):
        return value

    if isinstance(value, (list, tuple)):
        return Translations(fields=value) if value else None

    model = getattr(studio, "model", None)

    if model is not None and detect_adapter(model) is not None:
        return Translations()

    return None


def detect_adapter(model) -> Optional[type[TranslationAdapter]]:
    for adapter in (ParlerAdapter, ModelTranslationAdapter):
        if adapter.detect(model):
            return adapter

    return None


def resolve_adapter(model, config: Translations) -> TranslationAdapter:
    adapter = config.adapter

    if isinstance(adapter, str):
        adapter_class = ADAPTERS[adapter]
    elif adapter is not None:
        adapter_class = adapter
    else:
        adapter_class = detect_adapter(model) or ColumnsAdapter

    return adapter_class(model, config)


def build_translation_config(studio) -> Optional[TranslationConfig]:
    model = getattr(studio, "model", None)
    config = get_studio_translations(studio)

    if model is None or config is None:
        return None

    adapter = resolve_adapter(model, config)
    available = get_content_languages()

    if config.languages is not None:
        names = dict(available)
        languages = [(code, names.get(code, code)) for code in config.languages]
    else:
        languages = available

    if not languages or not adapter.fields():
        return None

    default = languages[0][0]
    # Languages no field has a column for are left out.
    languages = [
        (code, name)
        for code, name in languages
        if code == default
        or any(adapter.has_column(field, code, default) for field in adapter.fields())
    ]
    required = config.required if config.required is not None else [default]

    return TranslationConfig(
        adapter, languages, [code for code in required if code in dict(languages)]
    )


def get_translation_config(target) -> Optional[TranslationConfig]:
    """The translations of a studio, or of a model's registered studio."""
    if isinstance(target, type) and issubclass(target, models.Model):
        studio = cs_settings.ADMIN_SITE._registry.get(target)
    else:
        studio = target

    if studio is None:
        return None

    return build_translation_config(studio)


def serialize_translations(studio) -> Optional[dict[str, Any]]:
    config = build_translation_config(studio)

    return config.serialize() if config else None


def translated_label(model, name: str, label) -> Any:
    """
    A translation column's label with its language, such as
    "title (Dutch)"; other fields keep theirs.
    """
    config = get_translation_config(model)

    if config is None:
        return label

    found = config.column_languages().get(name)

    if found is None:
        return label

    field, code = found
    base = config.adapter.model_field(field)
    # With a column for every language (title_en) the field has no
    # model field of its own to take a label from.
    base_label = (
        base.verbose_name
        if base is not None and base.name == field
        else field.replace("_", " ")
    )

    return f"{base_label} ({config.language_name(code)})"


class MissingTranslationFilter(ListFilter):
    """
    "Missing translation": objects with a translated field left empty
    in the picked languages. Studios with translations get it without
    listing it; list it in list_filter to place it yourself.
    """

    title = _("Missing translation")
    parameter_name = "missing_translation"
    multiple = True

    def get_options(self, request):
        config = build_translation_config(self.studio)

        if config is None:
            return []

        # Required languages cannot be saved incomplete.
        return [
            (code, name)
            for code, name in config.languages
            if code not in config.required
        ]

    def queryset(self, request, queryset, value):
        config = build_translation_config(self.studio)

        if config is None:
            return queryset

        query = Q()

        for code in value:
            query |= config.missing_q(code)

        return queryset.filter(query).distinct()


SEARCH_PREFIXES = "^=@$"


def get_search_fields(studio, search_fields=None) -> list[str]:
    """
    A studio's search_fields with each translated field searched in
    every language: "title" also finds a Dutch or German title.
    """
    search_fields = list(
        search_fields
        if search_fields is not None
        else getattr(studio, "search_fields", None) or []
    )
    config = build_translation_config(studio)

    if config is None:
        return search_fields

    expanded = []

    for entry in search_fields:
        prefix = entry[0] if entry and entry[0] in SEARCH_PREFIXES else ""
        name = entry[len(prefix) :]

        if name in config.fields:
            lookups = config.adapter.search_lookups(name, config.codes, config.default)
            expanded.extend(
                f"{prefix}{lookup}"
                for lookup in lookups
                if f"{prefix}{lookup}" not in expanded
            )
        elif entry not in expanded:
            expanded.append(entry)

    return expanded
