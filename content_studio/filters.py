import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Optional, Union

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils.dateparse import parse_duration
from django.utils.text import capfirst
from rest_framework.exceptions import ParseError
from rest_framework.filters import BaseFilterBackend

from ._types import StrOrPromise
from .utils import flatten


class ListFilter:
    """
    A filter of the list page that is not a model field, like Django's
    SimpleListFilter. The admin shows it as a dropdown of its options.

        class DecadeFilter(ListFilter):
            title = "Decade"
            parameter_name = "decade"
            options = [("80s", "The 80s"), ("90s", "The 90s")]

            def queryset(self, request, queryset, value):
                start = {"80s": 1980, "90s": 1990}[value]
                return queryset.filter(year__gte=start, year__lt=start + 10)

    `options` are (value, label) pairs; override `get_options(request)`
    to build them at request time. With `multiple = True` editors pick
    several options and `queryset` receives a list of values; otherwise
    it receives one. Only values among the options reach `queryset`.
    """

    # The filter's label on the list page.
    title: Optional[StrOrPromise] = None

    # The query parameter that carries the filter's value.
    parameter_name: Optional[str] = None

    # The options, as (value, label) pairs.
    options: Iterable[tuple[Any, Any]] = ()

    # Whether editors pick one option or several.
    multiple: bool = False

    def __init__(self, studio):
        self.studio = studio

    def get_options(self, request) -> Iterable[tuple[Any, Any]]:
        return self.options

    def queryset(self, request, queryset, value):
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement queryset()."
        )


class DjangoSimpleListFilter(ListFilter):
    """
    Runs a Django SimpleListFilter subclass as a ListFilter: its lookups()
    are the options and its queryset() reads the value from self.value(),
    as on the classic admin. Single choice, like there.
    """

    multiple = False

    def __init__(self, studio, filter_class):
        super().__init__(studio)
        self.filter_class = filter_class
        self.title = filter_class.title
        self.parameter_name = filter_class.parameter_name

    def _instance(self, request, value=None):
        params = {} if value is None else {self.parameter_name: [value]}
        model = getattr(self.studio, "model", None)

        return self.filter_class(request, params, model, self.studio)

    def get_options(self, request):
        return self._instance(request).lookup_choices

    def queryset(self, request, queryset, value):
        return self._instance(request, value).queryset(request, queryset)


def is_django_simple_list_filter(entry) -> bool:
    try:
        from django.contrib.admin import SimpleListFilter
    except ImportError:  # pragma: no cover
        return False

    return isinstance(entry, type) and issubclass(entry, SimpleListFilter)


def is_list_filter_class(entry) -> bool:
    return isinstance(entry, type) and issubclass(entry, ListFilter)


def make_custom_filter(studio, entry) -> Optional[ListFilter]:
    """A list_filter entry as a ListFilter instance, or None for fields."""
    if is_list_filter_class(entry):
        return entry(studio)

    if is_django_simple_list_filter(entry):
        return DjangoSimpleListFilter(studio, entry)

    return None


def option_value(value) -> str:
    """An option's value as it travels in the query string."""
    if isinstance(value, bool):
        return "true" if value else "false"

    return str(value)


def serialize_options(options) -> list[list[str]]:
    return [[option_value(value), str(label)] for value, label in options or ()]


class FilterPathError(ValueError):
    pass


def get_studio_for(model):
    from .settings import cs_settings

    site = getattr(cs_settings, "ADMIN_SITE", None)

    return site._registry.get(model) if site is not None else None


def is_protected_field(model, field, studio=None) -> bool:
    """
    Whether a filter may not read or cross the field: the user model's
    password, and fields the model's studio leaves out with exclude.
    """
    from django.contrib.auth import get_user_model

    name = getattr(field, "name", None)

    if model is get_user_model() and name == "password":
        return True

    if studio is None:
        studio = get_studio_for(model)

    exclude = getattr(studio, "exclude", None) or []

    return name in exclude or getattr(field, "attname", None) in exclude


def resolve_filter_path(model, path: str, studio=None) -> list:
    """
    The model fields of a list_filter path such as "author__country",
    one per part. Every part but the last must be a relation; no part
    may be a protected field (is_protected_field). Raises
    FilterPathError with the reason otherwise.
    """
    from django.contrib.contenttypes.fields import GenericForeignKey

    fields = []
    current = model
    parts = path.split("__")

    for index, part in enumerate(parts):
        if current is None:
            raise FilterPathError(
                f"'{path}' continues past '{parts[index - 1]}', which is "
                "not a relation."
            )

        try:
            field = current._meta.pk if part == "pk" else current._meta.get_field(part)
        except FieldDoesNotExist:
            raise FilterPathError(
                f"'{path}': {current._meta.label_lower} has no field '{part}'."
            )

        if isinstance(field, GenericForeignKey):
            raise FilterPathError(
                f"'{path}': '{part}' is a generic relation, which cannot "
                "be filtered on."
            )

        if is_protected_field(current, field, studio if index == 0 else None):
            raise FilterPathError(
                f"'{path}': '{part}' of {current._meta.label_lower} is "
                "excluded from the admin and cannot be filtered on."
            )

        fields.append(field)
        current = field.related_model if field.is_relation else None

    return fields


def filter_path_label(fields) -> str:
    """'Author country' for author__country: the joined verbose names."""
    names = []

    for field in fields:
        verbose_name = getattr(field, "verbose_name", None)

        if verbose_name is None:
            # A reverse relation names its related model.
            verbose_name = field.related_model._meta.verbose_name

        names.append(str(verbose_name))

    return capfirst(" ".join(names[:1] + [n.lower() for n in names[1:]]))


@dataclass
class FieldFilterSpec:
    path: str
    fields: list

    @property
    def field(self):
        return self.fields[-1]


@dataclass
class CustomFilterSpec:
    filter: ListFilter

    @property
    def name(self) -> str:
        return self.filter.parameter_name


def get_filter_specs(
    studio, model=None
) -> list[Union[FieldFilterSpec, CustomFilterSpec]]:
    """
    The usable list_filter entries of a studio: field paths that resolve
    (a (field, class) tuple counts as its field; the class is ignored)
    and custom filters. Anything else is skipped here and reported by
    the system checks.
    """
    model = model or getattr(studio, "model", None)
    specs = []

    for entry in getattr(studio, "list_filter", None) or []:
        if isinstance(entry, (tuple, list)) and entry and isinstance(entry[0], str):
            entry = entry[0]

        if isinstance(entry, str):
            if model is None:
                continue
            try:
                fields = resolve_filter_path(model, entry, studio)
            except FilterPathError:
                continue
            specs.append(FieldFilterSpec(entry, fields))
            continue

        custom = make_custom_filter(studio, entry)

        if custom is not None and custom.parameter_name:
            specs.append(CustomFilterSpec(custom))

    return specs


def get_custom_filter(studio, name: str) -> Optional[ListFilter]:
    for spec in get_filter_specs(studio):
        if isinstance(spec, CustomFilterSpec) and spec.name == name:
            return spec.filter

    return None


def get_filter_field_path(studio, path: str) -> Optional[FieldFilterSpec]:
    for spec in get_filter_specs(studio):
        if isinstance(spec, FieldFilterSpec) and spec.path == path:
            return spec

    return None


def serialize_list_filters(studio, request) -> list[dict[str, Any]]:
    """The list page's filters, for the admin's model info."""
    from .serializers import ModelSerializer

    serialized = []

    for spec in get_filter_specs(studio):
        if isinstance(spec, CustomFilterSpec):
            serialized.append(
                {
                    "name": spec.name,
                    "label": str(spec.filter.title or spec.name),
                    "custom": True,
                    "multiple": bool(spec.filter.multiple),
                }
            )
            continue

        field = spec.field

        if isinstance(field, models.Field):
            data = ModelSerializer(field.model).get_field(field)
        else:
            # A reverse relation filters like a many-to-many field.
            data = {
                "type": "ManyToManyField",
                "related_model": field.related_model._meta.label_lower,
            }

        data["verbose_name"] = filter_path_label(spec.fields)

        serialized.append(
            {"name": spec.path, "label": data["verbose_name"], "field": data}
        )

    return serialized


class LookupFilter(BaseFilterBackend):
    """
    The list filter backend. Filters on the field paths declared in the
    studio's list_filter, with any lookup the path's last field
    registers, and runs its custom filters (ListFilter classes).
    Automatically handles multi-value lookups and booleans. Also
    supports exclusion of field filters.
    """

    MULTI_VALUE_LOOKUPS = ["in", "range"]

    EXCLUDE_SYMBOL = "~"

    NON_FILTER_FIELDS = [
        "search",
        "limit",
        "page",
        "ordering",
        "export_format",
        "export_scope",
        "export_mode",
    ]

    def get_allowed_fields(self, view):
        """
        Filterable field paths are declared by the model studio's
        list_filter: field names and paths across relations
        ("author__country"); a (field, class) tuple counts as its
        field. Filter classes are custom filters, not fields.

        Inline viewsets can always filter on their parent FK, in both
        its field name and attname (e.g. `article` / `article_id`)
        forms: inline lists only exist in the context of a parent.
        """
        admin_model = view._admin_model
        list_filter = getattr(admin_model, "list_filter", None) or []

        allowed = []
        for entry in list_filter:
            if isinstance(entry, (tuple, list)) and entry:
                entry = entry[0]
            if isinstance(entry, str):
                allowed.append(entry)

        parent_fk = getattr(view, "parent_fk", None)
        if parent_fk:
            allowed += [parent_fk, f"{parent_fk}_id"]

        return allowed

    def get_custom_filters(self, view) -> dict[str, ListFilter]:
        return {
            spec.name: spec.filter
            for spec in get_filter_specs(view._admin_model, model=view.queryset.model)
            if isinstance(spec, CustomFilterSpec)
        }

    def filter_queryset(self, request, queryset, view):
        """
        Build the queryset based on the query params and the view's model.
        Only apply filters in list endpoints (and moves, whose up and
        down steps follow the filtered list, and exports, which write
        the filtered list), and only on what the model studio declared
        in list_filter.
        """
        if getattr(view, "action", None) in ("list", "move", "export"):
            # An inline list filters on its parent itself.
            query_params = request.query_params.copy()
            if hasattr(view, "get_parent_filter_keys"):
                for key in view.get_parent_filter_keys():
                    query_params.pop(key, None)

            custom_filters = self.get_custom_filters(view)
            custom_values = {}

            for name in list(query_params.keys()):
                if name in custom_filters:
                    custom_values[name] = query_params.getlist(name)
                    del query_params[name]
                elif name.removeprefix(self.EXCLUDE_SYMBOL) in custom_filters:
                    raise ParseError(
                        detail=f"Invalid filter parameters: the filter '{name[1:]}' "
                        "cannot be excluded."
                    )

            # Building the query is part of the validation: an invalid
            # lookup or value raises here rather than in a 500.
            try:
                filter_kwargs, exclude_kwargs = self.get_filter_kwargs(
                    model_class=view.queryset.model,
                    query_params=query_params,
                    allowed_fields=self.get_allowed_fields(view),
                    studio=view._admin_model,
                )
                queryset = queryset.filter(**filter_kwargs).exclude(**exclude_kwargs)

                for name, raw in custom_values.items():
                    queryset = self.apply_custom_filter(
                        request, queryset, custom_filters[name], raw
                    )

                return queryset.distinct()
            except ParseError:
                raise
            except Exception as e:
                raise ParseError(detail=f"Invalid filter parameters: {e}")

        return queryset

    def apply_custom_filter(self, request, queryset, list_filter, raw_values):
        """
        Run a custom filter with its value: one option, or a list of
        options for a multiple choice filter. Values that are not among
        the filter's options are refused.
        """
        name = list_filter.parameter_name
        values = [v for v in flatten([r.split(",") for r in raw_values]) if v]

        if not values:
            return queryset

        if not list_filter.multiple and len(values) > 1:
            raise ValueError(f"The filter '{name}' takes one value.")

        allowed = {
            option_value(value) for value, _ in list_filter.get_options(request) or ()
        }
        unknown = [v for v in values if v not in allowed]

        if unknown:
            raise ValueError(f"{unknown[0]!r} is not an option of the filter '{name}'.")

        result = list_filter.queryset(
            request, queryset, values if list_filter.multiple else values[0]
        )

        # Like Django's SimpleListFilter, None leaves the list unfiltered.
        return queryset if result is None else result

    @staticmethod
    def match_path(key, paths):
        """
        The declared path a query key filters on, and the rest of the
        key (its lookup, or what follows the path): the longest declared
        path that the key equals or continues with "__".
        """
        best = None

        for path in paths:
            if key == path or key.startswith(f"{path}__"):
                if best is None or len(path) > len(best):
                    best = path

        if best is None:
            return None, None

        return best, key[len(best) + 2 :]

    def get_filter_kwargs(self, model_class, query_params, allowed_fields, studio=None):
        if not allowed_fields:
            allowed_fields = []

        filter_kwargs = {}
        exclude_kwargs = {}

        for key, value in query_params.lists():
            if key in self.NON_FILTER_FIELDS:
                continue
            is_exclude = key.startswith(self.EXCLUDE_SYMBOL)
            if is_exclude:
                # Strip the exclude symbol so the field name
                # resolves normally.
                key = key[len(self.EXCLUDE_SYMBOL) :]
            # By default Django supports repeated multi-values (e.g. `a=1&a=2`)
            # but we allow for comma-seperated multi-values as well (e.g. `a=1,2`).
            value = flatten([param.split(",") for param in value])

            path, rest = self.match_path(key, allowed_fields)

            if path is None:
                raise FieldDoesNotExist(
                    f"Filtering on '{key.split('__')[0]}' is not allowed for this "
                    "model; add it to the model admin's list_filter."
                )

            # The path's fields; protected fields (excluded, the user's
            # password) are refused even when declared.
            fields = resolve_filter_path(model_class, path, studio)
            field = fields[-1]

            # Get the allowed lookups for the path's last field: a key is
            # the path with at most one of them. Anything longer on a
            # relation (author__password__gt) would filter on the related
            # model's fields; elsewhere it chains lookups
            # (title__icontains__exact), which no field supports.
            lookups = field.get_lookups().keys()

            if rest and ("__" in rest or rest not in lookups):
                if field.is_relation:
                    raise FieldDoesNotExist(
                        f"Filtering on '{key}' traverses into a related field; "
                        "only lookups on the declared field are allowed."
                    )
                raise FieldDoesNotExist(
                    f"Filtering on '{key}' is not allowed; "
                    "use the field name with at most one lookup."
                )

            lookup = rest or None
            field_name = path

            # Default to "in" lookup for multi values that do not
            # have an explicit lookup set.
            if len(value) > 1 and not lookup and "in" in lookups:
                lookup = "in"
                key = f"{key}__in"

            # Some lookups allow multiple values, otherwise
            # the first value is used.
            is_multi = lookup in self.MULTI_VALUE_LOOKUPS

            # A value the lookup cannot take fails here, as a 400, not
            # while the query runs: a range needs its two bounds, and a
            # regular expression must compile (the database would
            # otherwise raise, after the filter was built).
            if lookup == "range" and len(value) != 2:
                raise ValueError(
                    f"The range lookup on '{field_name}' needs two values, "
                    "a lower and an upper bound."
                )

            if lookup in ("regex", "iregex"):
                try:
                    re.compile(value[0])
                except re.error as error:
                    raise ValueError(
                        f"The regular expression for '{field_name}' is "
                        f"invalid: {error}."
                    )
            # Depending on the field type we cast the value to
            # its correct type (i.e. number, boolean, etc.).
            if is_multi:
                casted_value = [self.cast_field_value(v, field) for v in value]
            elif lookup == "isnull":
                casted_value = value[0].strip().lower() in ["1", "true", "on"]
            else:
                casted_value = self.cast_field_value(value[0], field)

            if is_exclude:
                exclude_kwargs[key] = casted_value
            else:
                filter_kwargs[key] = casted_value

        return filter_kwargs, exclude_kwargs

    def cast_field_value(self, value: str, field):
        """
        Cast a raw string value to the field's type.

        Values are passed through unchanged unless the field type
        requires a cast: relations take their target field's type,
        booleans and nulls match case-insensitively, numbers are cast to
        their numeric type, everything else is matched exactly as
        provided.
        """
        if field.is_relation:
            # A relation filters on its target field's values (usually
            # the related model's primary key).
            return field.target_field.to_python(value)

        lowered = value.strip().lower()

        if isinstance(field, models.BooleanField):
            if lowered in ["1", "true", "on"]:
                return True
            if lowered in ["0", "false", "off"]:
                return False
            # Django removed NullBooleanField: a nullable boolean is now a
            # BooleanField(null=True).
            if field.null and lowered in ["null", "none", "empty"]:
                return None

        if isinstance(field, models.IntegerField):
            return int(value)

        if isinstance(field, models.DecimalField):
            return Decimal(value)

        if isinstance(field, models.FloatField):
            return float(value)

        if isinstance(field, models.DurationField):
            # Django's lookups expect a timedelta: "1 day, 2:00:00",
            # "02:30:00", a number of seconds, or ISO 8601 ("PT2H").
            duration = parse_duration(value)

            if duration is None:
                raise ValueError(f"{value!r} is not a duration.")

            return duration

        return value
