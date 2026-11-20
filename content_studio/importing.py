"""
Import: create and update a studio's objects from a CSV, Excel (.xlsx)
or JSON file.

A model studio opts in with import_fields (the fields a file may set)
or allow_import (the fields the edit page writes). Rows are matched on
import_id_fields (the primary key by default): a match is updated,
other rows create objects. Every row goes through the edit page's
rules: the studio's serializer, the model's validation, the save hooks,
permissions and tenant scoping, and each change is logged like a save
in the admin.

An import is checked first: the preview saves every row inside a
transaction that is rolled back, and reports what would be created,
updated or left unchanged and which rows fail. The editor then imports
all rows, or only the valid ones.

Files with many rows run as a Django task when the project's task
backend runs tasks in the background; the file and the job's progress
wait in UPLOAD_FOLDER meanwhile.

The "For import" export (and the template, its header row) writes the
values as an import reads them: field names as headers, choice values,
primary keys (or the import_lookups field) for relations.
"""

import csv
import datetime
import importlib.util
import io
import json
import logging
import posixpath
import uuid
from decimal import Decimal
from typing import Any, Callable, Optional

from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, router, transaction
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone, translation
from django.utils.duration import duration_string
from django.utils.http import content_disposition_header
from django.utils.text import capfirst, slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from rest_framework.exceptions import ValidationError

from .contrib.status.registry import register_task
from .export import CHUNK_SIZE, FORMULA_PREFIXES, _Echo
from .fields import MultipleChoiceField, TagField
from .settings import cs_settings
from .utils import get_tenant_field_name, get_tenant_scoped_queryset

try:
    from django.tasks import task
except ImportError:  # Django < 6.0
    try:
        from django_tasks import task
    except ImportError:
        task = None

logger = logging.getLogger("content_studio.importing")

__all__: list[str] = []

CSV = "csv"
XLSX = "xlsx"
JSON = "json"

CONTENT_TYPES = {
    CSV: "text/csv; charset=utf-8",
    XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    JSON: "application/json",
}

# The failing rows a result lists; the count covers all of them.
MAX_FAILURES = 100

# How often (in rows) a background import records its progress.
PROGRESS_INTERVAL = 200

# Job states.
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

# Row outcomes.
CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"


def is_excel_available() -> bool:
    """Whether Excel files can be read and written: openpyxl is installed."""
    return importlib.util.find_spec("openpyxl") is not None


def get_import_formats() -> list[str]:
    """The formats an import reads, and the "For import" export writes."""
    return [CSV, XLSX, JSON] if is_excel_available() else [CSV, JSON]


def get_template_formats() -> list[str]:
    """The formats of the template: a header row, so no JSON."""
    return [CSV, XLSX] if is_excel_available() else [CSV]


def is_importable(studio) -> bool:
    """
    Whether a studio offers import: a model studio that sets
    import_fields or allow_import and is not a singleton. Inlines are
    never imported on their own.
    """
    from .admin import ModelStudio, get_is_singleton

    return (
        isinstance(studio, ModelStudio)
        and bool(getattr(studio, "import_fields", None) or studio.allow_import)
        and not get_is_singleton(studio)
    )


def can_import(studio, request) -> bool:
    """Whether the request may import: it may add or change objects."""
    return bool(
        studio.has_add_permission(request) or studio.has_change_permission(request)
    )


# Configuration


def get_id_field_names(studio) -> list[str]:
    """The fields rows are matched on: import_id_fields, or the primary key."""
    names = getattr(studio, "import_id_fields", None)

    return list(names) if names else [studio.model._meta.pk.name]


def is_pk_key(studio) -> bool:
    """Whether rows are matched on the primary key."""
    return get_id_field_names(studio) == [studio.model._meta.pk.name]


def get_lookups(studio) -> dict[str, str]:
    """The field of the related model each relation is given by, by name."""
    return dict(getattr(studio, "import_lookups", None) or {})


def _is_writable_model_field(studio, field, request) -> bool:
    """
    Whether a file may set a model field: a concrete field or a
    many-to-many field the edit page writes, other than the primary key,
    the tenant, files and write-only fields.
    """
    from .admin import (
        get_form_field_names,
        get_readonly_field_names,
        get_write_only_field_names,
    )

    if field.auto_created and not field.concrete:
        return False

    if field.primary_key or isinstance(field, models.FileField):
        return False

    if not field.editable and not field.many_to_many:
        return False

    if field.name == get_tenant_field_name(studio.model):
        return False

    if field.name in get_write_only_field_names(studio, studio.model):
        return False

    if request is not None:
        if field.name in get_readonly_field_names(studio, request):
            return False

        if field.name not in get_form_field_names(studio, request):
            return False

    return True


def get_import_fields(studio, request) -> list:
    """
    The model fields a file may set, in order: import_fields, or the
    model's fields the edit page writes.
    """
    model = studio.model
    names = getattr(studio, "import_fields", None)

    if names:
        fields = []

        for name in names:
            try:
                fields.append(model._meta.get_field(name))
            except FieldDoesNotExist:
                continue
    else:
        fields = list(model._meta.concrete_fields) + list(model._meta.many_to_many)

    return [
        field for field in fields if _is_writable_model_field(studio, field, request)
    ]


def get_columns(studio, request) -> list:
    """
    The columns of the "For import" export and the template, as model
    fields: the fields rows are matched on, then the import fields.
    """
    model = studio.model
    columns = []

    for name in get_id_field_names(studio):
        try:
            columns.append(model._meta.get_field(name))
        except FieldDoesNotExist:
            continue

    for field in get_import_fields(studio, request):
        if field not in columns:
            columns.append(field)

    return columns


def serialize_import(studio, request) -> Optional[dict[str, Any]]:
    """What the list page needs to offer import, or None."""
    if not is_importable(studio):
        return None

    lookups = get_lookups(studio)
    pk_name = studio.model._meta.pk.name

    return {
        "formats": get_import_formats(),
        "template_formats": get_template_formats(),
        "key": get_id_field_names(studio),
        "columns": [
            {
                "name": field.name,
                "label": capfirst(str(field.verbose_name)),
                # The related model's field the column holds.
                "lookup": lookups.get(field.name) if field.is_relation else None,
                "required": (
                    field.name != pk_name
                    and not field.blank
                    and not field.has_default()
                    and not field.many_to_many
                ),
            }
            for field in get_columns(studio, request)
        ],
        "can_import": can_import(studio, request),
        "can_create": bool(studio.has_add_permission(request)),
        "can_update": bool(studio.has_change_permission(request)),
    }


# Values out: the "For import" export


def _related_value(related, lookup: Optional[str]):
    if related is None:
        return None

    return related.pk if not lookup or lookup == "pk" else getattr(related, lookup)


def get_raw_value(field, obj, lookups: dict[str, str]):
    """A model field's value as an import reads it back."""
    lookup = lookups.get(field.name)

    if field.many_to_many:
        return [
            _related_value(related, lookup)
            for related in getattr(obj, field.name).all()
        ]

    if field.is_relation:
        return _related_value(getattr(obj, field.name), lookup)

    value = field.value_from_object(obj)

    if isinstance(value, models.fields.files.FieldFile):
        return value.name or None

    return value


def _is_list_field(field) -> bool:
    """A field whose value is a list of plain values, written comma-separated."""
    return field.many_to_many or isinstance(field, (TagField, MultipleChoiceField))


def to_raw_cell(field, value, native: bool = False):
    """
    A raw value as a CSV (or, with native, Excel) cell: booleans read
    true or false, dates are ISO, lists of plain values are comma
    separated (JSON when a value holds a comma), other structures JSON.
    In CSV, text a spreadsheet would read as a formula is prefixed with
    an apostrophe, which the import removes again.
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        return value if native else ("true" if value else "false")

    if isinstance(value, (int, float, Decimal)):
        return value if native else str(value)

    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)

        return value.replace(tzinfo=None) if native else value.isoformat()

    if isinstance(value, (datetime.date, datetime.time)):
        return value if native else value.isoformat()

    if isinstance(value, datetime.timedelta):
        return duration_string(value)

    if isinstance(value, uuid.UUID):
        return str(value)

    if _is_list_field(field) and isinstance(value, (list, tuple)):
        items = [str(item) for item in value]

        if any("," in item for item in items):
            value = json.dumps(items, ensure_ascii=False)
        else:
            value = ", ".join(items)
    elif isinstance(value, (dict, list, tuple)) or isinstance(field, models.JSONField):
        value = json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)

    value = str(value)

    if not native and value.startswith(FORMULA_PREFIXES):
        value = f"'{value}"

    return value


def get_export_filename(studio, extension: str, template: bool = False) -> str:
    name = slugify(str(studio.model._meta.verbose_name_plural)) or "export"
    suffix = "import-template" if template else f"{timezone.localdate().isoformat()}"
    return f"{name}-{suffix}.{extension}"


def iter_raw_rows(studio, request, queryset, native: bool = False):
    """The header row of field names, then one row per object."""
    from .export import fetch_related
    from .form import TableColumn

    columns = get_columns(studio, request)
    lookups = get_lookups(studio)

    yield [field.name for field in columns]

    if queryset is None:
        return

    queryset = fetch_related(
        studio, queryset, [TableColumn(field=field.name) for field in columns]
    )

    for obj in queryset.iterator(chunk_size=CHUNK_SIZE):
        yield [
            to_raw_cell(field, get_raw_value(field, obj, lookups), native=native)
            for field in columns
        ]


def raw_export_response(studio, request, queryset, export_format: str):
    """
    The "For import" export of queryset, or with queryset None the
    template (the header row only), as a download.
    """
    template = queryset is None
    filename = get_export_filename(studio, export_format, template=template)

    if export_format == JSON:
        response = StreamingHttpResponse(
            _iter_json(studio, request, queryset), content_type=CONTENT_TYPES[JSON]
        )
    elif export_format == XLSX:
        response = HttpResponse(
            _xlsx_bytes(studio, iter_raw_rows(studio, request, queryset, native=True)),
            content_type=CONTENT_TYPES[XLSX],
        )
    else:
        writer = csv.writer(_Echo())

        def stream():
            yield "﻿"

            for row in iter_raw_rows(studio, request, queryset):
                yield writer.writerow(row)

        response = StreamingHttpResponse(stream(), content_type=CONTENT_TYPES[CSV])

    response["Content-Disposition"] = content_disposition_header(True, filename)
    return response


def _iter_json(studio, request, queryset):
    """The objects as a JSON list of objects keyed by field name."""
    from .export import fetch_related
    from .form import TableColumn

    columns = get_columns(studio, request)
    lookups = get_lookups(studio)
    encoder = DjangoJSONEncoder(ensure_ascii=False, indent=2)

    yield "["

    if queryset is not None:
        queryset = fetch_related(
            studio, queryset, [TableColumn(field=field.name) for field in columns]
        )
        first = True

        for obj in queryset.iterator(chunk_size=CHUNK_SIZE):
            item = {}

            for field in columns:
                value = get_raw_value(field, obj, lookups)

                if isinstance(value, datetime.datetime) and timezone.is_aware(value):
                    value = timezone.localtime(value)

                item[field.name] = value

            yield ("\n" if first else ",\n") + encoder.encode(item)
            first = False

    yield "\n]\n"


def _xlsx_bytes(studio, rows) -> bytes:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font

    workbook = Workbook(write_only=True)
    title = "".join(
        char
        for char in capfirst(str(studio.model._meta.verbose_name_plural))
        if char not in "[]:*?/\\"
    )
    sheet = workbook.create_sheet(title=title[:31] or "Import")
    bold = Font(bold=True)

    def cell(value, header=False):
        if isinstance(value, str):
            value = ILLEGAL_CHARACTERS_RE.sub("", value)

        result = WriteOnlyCell(sheet, value=value)

        if header:
            result.font = bold
        elif isinstance(value, datetime.datetime):
            result.number_format = "yyyy-mm-dd hh:mm:ss"
        elif isinstance(value, datetime.date):
            result.number_format = "yyyy-mm-dd"
        elif isinstance(value, datetime.time):
            result.number_format = "hh:mm:ss"
        elif isinstance(value, str):
            # Text stays text: never a formula.
            result.data_type = "s"

        return result

    rows = iter(rows)
    sheet.append([cell(header, header=True) for header in next(rows)])

    for row in rows:
        sheet.append([cell(value) for value in row])

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


# Reading files


class ImportFileError(Exception):
    """A file that cannot be imported at all; the message says why."""


def detect_format(name: str, content_type: Optional[str] = None) -> str:
    """The format of an uploaded file, by its extension."""
    extension = posixpath.splitext((name or "").lower())[1].lstrip(".")

    if extension in (CSV, "txt", "tsv"):
        return CSV

    if extension == XLSX:
        if not is_excel_available():
            raise ImportFileError(_("Excel files cannot be imported on this site."))
        return XLSX

    if extension == JSON:
        return JSON

    raise ImportFileError(_("Choose a CSV, Excel (.xlsx) or JSON file."))


# The most columns a file may have: more is not a sheet of objects.
MAX_COLUMNS = 1000

# How many times IMPORT_MAX_SIZE an Excel file may unpack to: a .xlsx is
# a zip, so a small file can hold a huge sheet.
XLSX_MAX_EXPANSION = 10


def file_max_rows() -> Optional[int]:
    """
    The most rows any import reads: IMPORT_FILE_MAX_ROWS, and in the
    request also IMPORT_MAX_ROWS when no background worker takes larger
    files.
    """
    limits = [cs_settings.IMPORT_FILE_MAX_ROWS]

    if not runs_in_background():
        limits.append(cs_settings.IMPORT_MAX_ROWS)

    limits = [limit for limit in limits if limit is not None]
    return min(limits) if limits else None


class TooManyRows(ImportFileError):
    def __init__(self, max_rows: int):
        self.max_rows = max_rows
        super().__init__(
            _(
                "The file has more than %(max)s rows; at most %(max)s can be "
                "imported at once. Split it into smaller files."
            )
            % {"max": f"{max_rows:,}"}
        )


def read_rows(
    content: bytes, file_format: str, max_rows: Optional[int] = None
) -> tuple[list[str], list[tuple[int, dict]]]:
    """
    The headers and rows of a file: each row as its number (the line in
    a spreadsheet, the position in a JSON list) and its values by header.
    Rows without any value are skipped. Reading stops, with TooManyRows,
    at the first row beyond max_rows, so a huge file is never parsed
    whole; more than MAX_COLUMNS headers is refused too.
    """
    if file_format == JSON:
        headers, rows = _read_json(content, max_rows)
    elif file_format == XLSX:
        headers, rows = _read_xlsx(content, max_rows)
    else:
        headers, rows = _read_csv(content, max_rows)

    return headers, rows


def _check_columns(headers) -> None:
    if len(headers) > MAX_COLUMNS:
        raise ImportFileError(
            _("The file has more than %(max)s columns.") % {"max": MAX_COLUMNS}
        )


def _add_row(rows: list, row, max_rows: Optional[int]) -> None:
    if max_rows is not None and len(rows) >= max_rows:
        raise TooManyRows(max_rows)

    rows.append(row)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Spreadsheet applications on Windows save CSV in the system's
        # code page.
        return content.decode("cp1252", errors="replace")


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _read_csv(content: bytes, max_rows: Optional[int] = None):
    text = _decode(content)

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)

    try:
        headers = [header.strip() for header in next(reader)]
    except StopIteration:
        raise ImportFileError(_("The file is empty."))
    except csv.Error:
        raise ImportFileError(_("The file is not a valid CSV file."))

    _check_columns(headers)
    rows: list = []

    try:
        for index, values in enumerate(reader, start=2):
            if all(_is_blank(value) for value in values):
                continue

            _add_row(rows, (index, _row_dict(headers, values)), max_rows)
    except csv.Error:
        raise ImportFileError(_("The file is not a valid CSV file."))

    return headers, rows


def _row_dict(headers, values) -> dict:
    return {
        header: values[position] if position < len(values) else None
        for position, header in enumerate(headers)
        if header
    }


def _check_xlsx_size(content: bytes) -> None:
    """
    Refuse an Excel file that unpacks to more than XLSX_MAX_EXPANSION
    times IMPORT_MAX_SIZE: openpyxl reads the shared strings whole.
    """
    import zipfile

    max_size = cs_settings.IMPORT_MAX_SIZE

    if max_size is None:
        return

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            unpacked = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, ValueError):
        raise ImportFileError(_("The file is not a valid Excel file."))

    if unpacked > max_size * XLSX_MAX_EXPANSION:
        raise ImportFileError(_("The Excel file is too large to import."))


def _read_xlsx(content: bytes, max_rows: Optional[int] = None):
    from openpyxl import load_workbook

    _check_xlsx_size(content)

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise ImportFileError(_("The file is not a valid Excel file."))

    try:
        sheet = workbook.worksheets[0]
        values = sheet.iter_rows(values_only=True)

        try:
            headers = [
                "" if header is None else str(header).strip() for header in next(values)
            ]
        except StopIteration:
            raise ImportFileError(_("The file is empty."))

        _check_columns(headers)
        rows: list = []

        for index, row in enumerate(values, start=2):
            if all(_is_blank(value) for value in row):
                continue

            _add_row(rows, (index, _row_dict(headers, list(row))), max_rows)
    finally:
        workbook.close()

    return headers, rows


def _read_json(content: bytes, max_rows: Optional[int] = None):
    try:
        data = json.loads(_decode(content))
    except (ValueError, RecursionError):
        raise ImportFileError(_("The file is not valid JSON."))

    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ImportFileError(_("A JSON file must hold a list of objects."))

    rows: list = []

    for index, item in enumerate(data, start=1):
        if item:
            _add_row(rows, (index, item), max_rows)

    headers: list[str] = []
    seen: set[str] = set()

    for _index, item in rows:
        for key in item:
            if key not in seen:
                seen.add(key)
                headers.append(str(key))

                if len(headers) > MAX_COLUMNS:
                    _check_columns(headers)

    return headers, rows


# Columns


def map_columns(studio, request, headers) -> tuple[dict[str, Any], list[str]]:
    """
    The model field each header names, and the headers that are left
    out. A header is a field name ("id" and "pk" name the primary key)
    or, ignoring case, its name or verbose name; columns for fields an
    import cannot set are left out.
    """
    model = studio.model
    pk = model._meta.pk
    candidates = {field.name: field for field in get_import_fields(studio, request)}

    for name in get_id_field_names(studio):
        try:
            candidates.setdefault(name, model._meta.get_field(name))
        except FieldDoesNotExist:
            continue

    by_name = {name.lower(): field for name, field in candidates.items()}
    by_label = {}

    for field in candidates.values():
        by_label.setdefault(str(field.verbose_name).strip().lower(), field)

    if pk.name in candidates:
        by_name.setdefault("id", pk)
        by_name.setdefault("pk", pk)

    columns, ignored, used = {}, [], set()

    for header in headers:
        key = header.strip().lower()
        field = by_name.get(key) or by_label.get(key)

        if not header.strip():
            continue

        if field is None or field.name in used:
            ignored.append(header)
            continue

        columns[header] = field
        used.add(field.name)

    return columns, ignored


# Values in


class RowError(Exception):
    """A value of a row that cannot be read, by field."""

    def __init__(self, field_name: str, message: str):
        self.field_name = field_name
        self.message = message
        super().__init__(message)


TRUE_VALUES = {"true", "1", "yes", "y", "on", "x"}
FALSE_VALUES = {"false", "0", "no", "n", "off"}


def _unescape(value):
    """Strings without surrounding space or the CSV formula prefix."""
    if not isinstance(value, str):
        return value

    value = value.strip()

    if len(value) > 1 and value[0] == "'" and value[1] in FORMULA_PREFIXES:
        return value[1:]

    return value


def _number(value):
    """Spreadsheet numbers: 3.0 is the integer 3."""
    if isinstance(value, float) and value.is_integer():
        return int(value)

    return value


def _split_list(value) -> list:
    """A list from a cell: a JSON list, or comma-separated values."""
    if isinstance(value, (list, tuple)):
        return list(value)

    if isinstance(value, str):
        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except ValueError:
                parsed = None

            if isinstance(parsed, list):
                return parsed

        return [item.strip() for item in value.split(",") if item.strip()]

    return [value]


def _string_choice(field, value, choices):
    """A choice's value from its value or, ignoring case, its label."""
    text = str(_number(value))

    for choice_value, _label in choices:
        if str(choice_value) == text:
            return choice_value

    matches = [
        choice_value
        for choice_value, label in choices
        if str(label).strip().lower() == text.lower()
    ]

    if len(matches) == 1:
        return matches[0]

    # Not a known choice: the serializer reports it.
    return value


def _flat_choices(field):
    if isinstance(field, MultipleChoiceField):
        return [(value, label) for value, label in field.options]

    return list(field.flatchoices or [])


class ValueReader:
    """Turns a row's cells into the values the studio's serializer takes."""

    def __init__(self, studio, request, file_format: str):
        self.studio = studio
        self.request = request
        self.file_format = file_format
        self.lookups = get_lookups(studio)
        self._related_cache: dict = {}

    def read(self, field, value):
        if not isinstance(value, (dict, list)) or self.file_format != JSON:
            value = _unescape(value)

        if field.many_to_many:
            if _is_blank(value):
                return []

            return [
                {"id": self.related_pk(field, item)}
                for item in _split_list(value)
                if not _is_blank(item)
            ]

        if field.is_relation:
            if _is_blank(value):
                return None

            return {"id": self.related_pk(field, value)}

        if isinstance(field, (TagField, MultipleChoiceField)):
            if _is_blank(value):
                return []

            items = [str(_number(item)).strip() for item in _split_list(value)]

            if isinstance(field, MultipleChoiceField):
                choices = _flat_choices(field)
                items = [_string_choice(field, item, choices) for item in items]

            return items

        if _is_blank(value):
            # An empty text field is the empty string, as on the edit page.
            return "" if _is_text_field(field) and not field.null else None

        if isinstance(field, models.BooleanField):
            return self.boolean(field, value)

        if field.choices:
            return _string_choice(field, value, _flat_choices(field))

        if isinstance(field, models.JSONField):
            if isinstance(value, str) and self.file_format != JSON:
                try:
                    return json.loads(value)
                except ValueError:
                    raise RowError(field.name, _("Enter valid JSON."))

            return value

        if isinstance(value, datetime.datetime):
            if isinstance(field, models.DateField) and not isinstance(
                field, models.DateTimeField
            ):
                return value.date().isoformat()

            return value.isoformat()

        if isinstance(value, (datetime.date, datetime.time)):
            return value.isoformat()

        if isinstance(value, float) and isinstance(
            field, (models.IntegerField, models.AutoField)
        ):
            return _number(value)

        if isinstance(value, (int, float, Decimal)) and _is_text_field(field):
            return str(_number(value))

        return value

    def boolean(self, field, value):
        if isinstance(value, bool):
            return value

        text = str(_number(value)).strip().lower()

        if text in TRUE_VALUES or text == _("Yes").lower():
            return True

        if text in FALSE_VALUES or text == _("No").lower():
            return False

        raise RowError(field.name, _("Enter true or false."))

    def related_pk(self, field, value):
        """
        The primary key of the related object a cell names: the value
        itself, or the object whose import_lookups field holds it.
        Related objects are found among the request's tenant.
        """
        value = _number(_unescape(value))
        lookup = self.lookups.get(field.name)

        if not lookup or lookup == "pk":
            if isinstance(value, dict) and "id" in value:
                return value["id"]
            return value

        key = (field.name, str(value))

        if key in self._related_cache:
            return self._related_cache[key]

        model = field.related_model
        queryset = get_tenant_scoped_queryset(
            self.request, model, model._default_manager.all()
        )

        try:
            pks = list(
                queryset.filter(**{lookup: value}).values_list("pk", flat=True)[:2]
            )
        except (DjangoValidationError, ValueError, TypeError):
            pks = []

        if not pks:
            raise RowError(
                field.name,
                _("No %(model)s with %(field)s %(value)s.")
                % {
                    "model": model._meta.verbose_name,
                    "field": _lookup_label(model, lookup),
                    "value": _quote(value),
                },
            )

        if len(pks) > 1:
            raise RowError(
                field.name,
                _("More than one %(model)s has %(field)s %(value)s.")
                % {
                    "model": model._meta.verbose_name,
                    "field": _lookup_label(model, lookup),
                    "value": _quote(value),
                },
            )

        self._related_cache[key] = pks[0]
        return pks[0]


def _is_text_field(field) -> bool:
    return isinstance(field, (models.CharField, models.TextField)) and not field.choices


def _lookup_label(model, lookup: str) -> str:
    try:
        return str(model._meta.get_field(lookup).verbose_name)
    except FieldDoesNotExist:
        return lookup


def _quote(value) -> str:
    return f"“{value}”"


# Running an import


def _flatten_messages(detail) -> list[str]:
    """The messages of a DRF error detail, nested ones joined."""
    if isinstance(detail, dict):
        messages = []

        for value in detail.values():
            messages.extend(_flatten_messages(value))

        return messages

    if isinstance(detail, (list, tuple)):
        messages = []

        for item in detail:
            messages.extend(_flatten_messages(item))

        return messages

    return [str(detail)]


class Importer:
    """
    Imports a file's rows through a model viewset: its queryset (the
    studio's, tenant scoped, without the trash), its serializer and its
    perform_create and perform_update, as the edit page saves.
    """

    def __init__(self, view, headers, rows, file_format: str):
        self.view = view
        self.request = view.request
        self.studio = view._admin_model
        self.model = view._model
        self.headers = headers
        self.rows = rows
        self.file_format = file_format
        self.columns, self.ignored = map_columns(self.studio, self.request, headers)
        self.reader = ValueReader(self.studio, self.request, file_format)
        self.id_fields = [
            self.model._meta.get_field(name) for name in get_id_field_names(self.studio)
        ]

    def check_columns(self) -> list[str]:
        """File-level problems: no known column, or missing key columns."""
        errors = []
        column_names = {field.name for field in self.columns.values()}
        import_names = column_names - {field.name for field in self.id_fields}

        if not is_pk_key(self.studio):
            missing = [
                field.name for field in self.id_fields if field.name not in column_names
            ]

            if missing:
                errors.append(
                    ngettext(
                        "The file needs the column %(columns)s to match rows.",
                        "The file needs the columns %(columns)s to match rows.",
                        len(missing),
                    )
                    % {"columns": ", ".join(missing)}
                )

        if not import_names and not errors:
            errors.append(
                _(
                    "The file has no column this import can set. Download the template for the columns."
                )
            )

        return errors

    def run(
        self,
        *,
        preview: bool,
        skip_errors: bool = False,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Import the rows: with preview, inside a transaction that is
        rolled back. Without skip_errors, a failing row rolls back the
        whole import.
        """
        result = {
            "preview": preview,
            "applied": False,
            "total": len(self.rows),
            CREATED: 0,
            UPDATED: 0,
            UNCHANGED: 0,
            "failed": 0,
            "failures": [],
            "ignored_columns": list(self.ignored),
            "errors": self.check_columns(),
        }

        if result["errors"]:
            result["failed"] = len(self.rows)
            return result

        self.view._import_preview = preview
        using = router.db_for_write(self.model)

        with transaction.atomic(using=using):
            for position, (number, row) in enumerate(self.rows, start=1):
                outcome, errors = self.import_row(row, using)

                if errors:
                    result["failed"] += 1

                    if len(result["failures"]) < MAX_FAILURES:
                        result["failures"].append({"row": number, "errors": errors})
                else:
                    result[outcome] += 1

                if progress is not None and (
                    position % PROGRESS_INTERVAL == 0 or position == len(self.rows)
                ):
                    progress(position, len(self.rows))

            if preview or (result["failed"] and not skip_errors):
                transaction.set_rollback(True, using=using)
            else:
                result["applied"] = True

        return result

    def import_row(self, row: dict, using) -> tuple[Optional[str], list[dict]]:
        """Import one row: its outcome, or its errors."""
        data, errors = {}, []
        key_values = {}

        for header, field in self.columns.items():
            value = row.get(header)

            if field in self.id_fields:
                key_values[field.name] = value

                if field.primary_key:
                    continue

            try:
                data[field.name] = self.reader.read(field, value)
            except RowError as error:
                errors.append(self.error(error.field_name, [error.message]))

        if errors:
            return None, errors

        try:
            instance = self.find(key_values)
        except RowError as error:
            return None, [self.error(error.field_name, [error.message])]

        if instance is None and not self.studio.has_add_permission(self.request):
            return None, [
                self.error(
                    None,
                    [
                        _("You may not create %(model)s.")
                        % {"model": self.model._meta.verbose_name_plural}
                    ],
                )
            ]

        if instance is not None and not self.studio.has_change_permission(
            self.request, instance
        ):
            return None, [
                self.error(
                    None,
                    [
                        _("You may not change this %(model)s.")
                        % {"model": self.model._meta.verbose_name}
                    ],
                )
            ]

        # Each row in a savepoint: a failing row leaves the others.
        try:
            with transaction.atomic(using=using):
                serializer = self.view.get_serializer(
                    instance, data=data, partial=instance is not None
                )

                if not serializer.is_valid():
                    raise ValidationError(serializer.errors)

                if instance is not None and is_unchanged(
                    instance, serializer.validated_data
                ):
                    return UNCHANGED, []

                if instance is None:
                    self.view.perform_create(serializer)
                    return CREATED, []

                self.view.perform_update(serializer)
                return UPDATED, []
        except ValidationError as error:
            return None, self.errors_of(error.detail)
        except DjangoValidationError as error:
            return None, [self.error(None, error.messages)]

    def find(self, key_values: dict):
        """
        The object a row updates, or None to create one. Rows are
        matched on the primary key (a blank one creates, an unknown one
        fails) or on import_id_fields (no match creates).
        """
        queryset = self.view.get_queryset()

        if all(_is_blank(_unescape(value)) for value in key_values.values()):
            return None

        lookup = {}

        for field in self.id_fields:
            value = _number(_unescape(key_values.get(field.name)))

            if field.is_relation:
                try:
                    value = self.reader.related_pk(field, value)
                except RowError:
                    if field.primary_key:
                        raise
                    return None

                name = field.attname
            else:
                name = field.name

            if _is_blank(value):
                value = None if field.null else ""

            try:
                lookup[name] = (
                    field.to_python(value) if not field.is_relation else value
                )
            except DjangoValidationError as error:
                raise RowError(field.name, " ".join(error.messages))

        try:
            matches = list(queryset.filter(**lookup)[:2])
        except (DjangoValidationError, ValueError, TypeError):
            matches = []

        if len(matches) > 1:
            raise RowError(
                None,
                _("The row matches more than one %(model)s.")
                % {"model": self.model._meta.verbose_name},
            )

        if matches:
            return matches[0]

        if is_pk_key(self.studio):
            raise RowError(
                self.model._meta.pk.name,
                _("No %(model)s with id %(value)s. Leave the id empty to create one.")
                % {
                    "model": self.model._meta.verbose_name,
                    "value": _quote(next(iter(key_values.values()))),
                },
            )

        return None

    def header_of(self, field_name) -> Optional[str]:
        for header, field in self.columns.items():
            if field.name == field_name:
                return header

        return None

    def error(self, field_name, messages) -> dict:
        return {
            "column": self.header_of(field_name) if field_name else None,
            "field": field_name,
            "messages": [str(message) for message in messages],
        }

    def errors_of(self, detail) -> list[dict]:
        if not isinstance(detail, dict):
            return [self.error(None, _flatten_messages(detail))]

        errors = []

        for name, value in detail.items():
            field_name = (
                None if name in ("non_field_errors", "__all__", "detail") else name
            )
            errors.append(self.error(field_name, _flatten_messages(value)))

        return errors


def is_unchanged(instance, validated_data: dict) -> bool:
    """Whether the validated values equal the object's current ones."""
    model = type(instance)

    for name, value in validated_data.items():
        try:
            field = model._meta.get_field(name)
        except FieldDoesNotExist:
            return False

        if field.many_to_many:
            current = {
                str(pk) for pk in getattr(instance, name).values_list("pk", flat=True)
            }
            new = {str(getattr(item, "pk", item)) for item in value or []}
        elif field.is_relation:
            current = getattr(instance, field.attname)
            new = getattr(value, "pk", value)
        else:
            current = field.value_from_object(instance)
            new = value

        if current != new:
            return False

    return True


# Background jobs


def runs_in_background() -> bool:
    """
    Whether imports can run as a task: Django tasks are available and
    the default backend runs them in the background (not the immediate
    backend, which runs them in place, or the dummy one, which never
    runs them).
    """
    if run_import_task is None:
        return False

    try:
        backend = run_import_task.get_backend()
        name = type(backend).__name__
    except Exception:
        return False

    return bool(name) and name not in ("ImmediateBackend", "DummyBackend")


def get_upload_storage():
    from . import uploads

    return uploads.get_upload_storage()


def job_folder() -> str:
    return posixpath.join(cs_settings.UPLOAD_FOLDER, "imports")


def _state_path(job_id: str) -> str:
    return posixpath.join(job_folder(), f"{job_id}.json")


def _file_path(job_id: str, file_format: str) -> str:
    return posixpath.join(job_folder(), f"{job_id}.{file_format}")


def save_state(state: dict) -> None:
    path = _state_path(state["id"])

    if get_upload_storage().exists(path):
        get_upload_storage().delete(path)

    get_upload_storage().save(
        path, ContentFile(json.dumps(state, cls=DjangoJSONEncoder).encode("utf-8"))
    )


def load_state(job_id: str) -> Optional[dict]:
    try:
        job_id = str(uuid.UUID(str(job_id)))
    except ValueError:
        return None

    path = _state_path(job_id)

    try:
        with get_upload_storage().open(path, "rb") as file:
            return json.loads(file.read().decode("utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None


def public_state(state: dict) -> dict:
    """What the editor sees of a job."""
    return {
        key: state.get(key)
        for key in ("id", "status", "preview", "processed", "total", "result", "error")
    }


def create_job(
    request,
    studio,
    content: bytes,
    file_format: str,
    filename: str,
    total: int,
    *,
    preview: bool,
    skip_errors: bool,
) -> dict:
    """Store the file and a job for it, and enqueue the task."""
    job_id = str(uuid.uuid4())
    get_upload_storage().save(_file_path(job_id, file_format), ContentFile(content))
    state = {
        "id": job_id,
        "user": str(request.user.pk),
        "model": studio.model._meta.label_lower,
        "tenant": request.headers.get("x-dcs-tenant"),
        "language": translation.get_language(),
        "format": file_format,
        "filename": filename,
        "status": QUEUED,
        "preview": preview,
        "skip_errors": skip_errors,
        "processed": 0,
        "total": total,
        "result": None,
        "error": None,
        "created_at": timezone.now(),
    }
    save_state(state)
    enqueue_job(state)
    return state


def enqueue_job(state: dict) -> None:
    job_id = state["id"]

    # Enqueued once the request's transaction (if any) commits.
    transaction.on_commit(lambda: run_import_task.enqueue(job_id))


def get_viewset_class(model):
    """The content viewset registered for a model."""
    from .router import content_studio_router

    prefix = f"api/content/{model._meta.label_lower}"

    for entry in content_studio_router.registry:
        if entry[0] == prefix:
            return entry[1]

    return None


def build_view(model, user, tenant: Optional[str], method: str = "POST"):
    """
    A content viewset for model with a request of user, as in the
    admin: for imports that run as a task, outside a request.
    """
    from django.http import HttpRequest
    from rest_framework.request import Request

    viewset_class = get_viewset_class(model)

    if viewset_class is None:
        return None

    http_request = HttpRequest()
    http_request.method = method
    http_request.META["SERVER_NAME"] = "localhost"
    http_request.META["SERVER_PORT"] = "80"

    if tenant:
        http_request.META["HTTP_X_DCS_TENANT"] = str(tenant)

    http_request.user = user
    request = Request(http_request)
    request.user = user

    view = viewset_class()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    view.action = "import_rows"
    view.headers = {}

    return view


def run_job(job_id: str) -> None:
    """Run a stored import job: the task's body."""
    from django.apps import apps
    from django.contrib.auth import get_user_model

    from .signals import collect_changes

    state = load_state(job_id)

    if state is None or state["status"] not in (QUEUED,):
        return

    state["status"] = RUNNING
    save_state(state)

    try:
        model = apps.get_model(state["model"])
        user = get_user_model()._default_manager.get(pk=state["user"])
        view = build_view(model, user, state.get("tenant"))

        if view is None or not is_importable(view._admin_model):
            raise ImportFileError(_("This model cannot be imported."))

        with get_upload_storage().open(
            _file_path(job_id, state["format"]), "rb"
        ) as file:
            content = file.read()

        with translation.override(state.get("language")):
            headers, rows = read_rows(
                content, state["format"], cs_settings.IMPORT_FILE_MAX_ROWS
            )
            importer = Importer(view, headers, rows, state["format"])

            def progress(processed, total):
                state["processed"] = processed
                state["total"] = total
                save_state(state)

            with collect_changes(view.request):
                result = importer.run(
                    preview=state["preview"],
                    skip_errors=state["skip_errors"],
                    progress=progress,
                )

        state["result"] = result
        state["status"] = DONE
    except ImportFileError as error:
        state["status"] = FAILED
        state["error"] = str(error)
    except Exception:
        logger.exception("The import %s failed.", job_id)
        state["status"] = FAILED
        state["error"] = _(
            "The import failed. Try again, or ask a developer to check the logs."
        )

    save_state(state)

    # The file is kept after a preview, for the import that follows it.
    if not state["preview"] or state["status"] == FAILED:
        delete_job_file(state)


def discard_job(state: dict) -> None:
    """
    An import the editor left after its check: its file and state are
    removed now, not when content_studio_clear_uploads runs.
    """
    delete_job_file(state)

    try:
        get_upload_storage().delete(_state_path(state["id"]))
    except (FileNotFoundError, OSError):
        pass


def delete_job_file(state: dict) -> None:
    path = _file_path(state["id"], state["format"])

    try:
        get_upload_storage().delete(path)
    except (FileNotFoundError, OSError):
        pass


def restart_job(state: dict, *, skip_errors: bool) -> dict:
    """The import that follows a background preview, on its stored file."""
    state.update(
        status=QUEUED,
        preview=False,
        skip_errors=skip_errors,
        processed=0,
        result=None,
        error=None,
    )
    save_state(state)
    enqueue_job(state)
    return state


def run_import(job_id: str) -> None:
    run_job(job_id)


# Workers import tasks by module and function name, so the task keeps
# the name of the function it wraps. Without Django tasks, imports run
# in the request only (runs_in_background is False).
run_import_task = task(run_import) if task is not None else None

# The system status page names the task when a task adapter lists it.
register_task(f"{__name__}.run_import", gettext_lazy("Import from a file"))
