"""
Reading a fixture to restore: a Content Studio backup, or any JSON file
made with manage.py dumpdata.

A plain dumpdata file names content types and permissions by their ids.
A restore empties the database, and migrate's signal handlers then make
the content types and permissions again, with other ids. So the file's
own content type and permission rows are left out, and every reference
to them is rewritten to their natural keys ([app_label, model] and
[codename, app_label, model]), which loaddata looks up. Rows a restore
never loads (sessions, the backups app's own records) are left out too.
"""

import bz2
import gzip
import json
import lzma
import posixpath
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from django.apps import apps
from django.db import models

# The compressions dumpdata writes (and loaddata reads), by suffix.
COMPRESSIONS = {
    ".gz": gzip.open,
    ".bz2": bz2.open,
    ".xz": lzma.open,
    ".lzma": lzma.open,
}

SUFFIXES = (".json", *(f".json{suffix}" for suffix in COMPRESSIONS))

CONTENT_TYPE = "contenttypes.contenttype"
PERMISSION = "auth.permission"

# Rows never loaded: migrate makes content types and permissions,
# sessions are short-lived and the backups app keeps its own records.
SKIPPED_MODELS = {
    CONTENT_TYPE,
    PERMISSION,
    "sessions.session",
    "password_reset.passwordresetcode",
}
SKIPPED_APPS = {"content_studio_backups"}


class FixtureError(Exception):
    pass


def fixture_suffix(name: str) -> Optional[str]:
    """The fixture suffix the name ends with (".json.gz"), or None."""
    lower = posixpath.basename(name).lower()

    for suffix in sorted(SUFFIXES, key=len, reverse=True):
        if lower.endswith(suffix):
            return suffix

    return None


def open_fixture(path: str, mode: str = "rt"):
    suffix = fixture_suffix(path)

    if suffix is None:
        raise FixtureError(
            "Only JSON fixtures can be restored: " + ", ".join(SUFFIXES) + "."
        )

    opener = COMPRESSIONS.get(suffix[len(".json") :])

    if opener is None:
        return open(path, mode, encoding="utf-8")

    return opener(path, mode, encoding="utf-8")


def read_fixture(path: str) -> list:
    try:
        with open_fixture(path) as file:
            rows = json.load(file)
    except FixtureError:
        raise
    except (OSError, EOFError, lzma.LZMAError, UnicodeDecodeError) as exc:
        raise FixtureError(f"The file could not be read: {exc}") from exc
    except ValueError as exc:
        raise FixtureError(f"The file is not valid JSON: {exc}") from exc

    if not isinstance(rows, list) or not all(
        isinstance(row, dict) and isinstance(row.get("model"), str) for row in rows
    ):
        raise FixtureError("The file is not a Django fixture: a list of rows.")

    return rows


def is_skipped(label: str) -> bool:
    label = label.lower()
    return label in SKIPPED_MODELS or label.partition(".")[0] in SKIPPED_APPS


@dataclass
class Fixture:
    """A fixture ready for loaddata, and what it holds."""

    rows: list
    counts: dict = field(default_factory=dict)
    # Rows left out (content types, permissions, sessions, records).
    skipped: int = 0
    # References to content types and permissions rewritten by name.
    remapped: int = 0
    # Model labels the file holds that are not installed.
    unknown_models: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def write(self, path: str) -> None:
        """Save it gzipped, for loaddata (path ends .json.gz)."""
        with gzip.open(path, "wt", encoding="utf-8") as file:
            json.dump(self.rows, file)


def _natural_keys(rows: list) -> tuple[dict, dict]:
    """The file's content type and permission ids, as natural keys."""
    content_types = {}

    for row in rows:
        if row["model"].lower() == CONTENT_TYPE and "pk" in row:
            fields = row.get("fields") or {}
            content_types[row["pk"]] = [fields.get("app_label"), fields.get("model")]

    permissions = {}

    for row in rows:
        if row["model"].lower() == PERMISSION and "pk" in row:
            fields = row.get("fields") or {}
            content_type = fields.get("content_type")

            if not isinstance(content_type, list):
                content_type = content_types.get(content_type)

            if content_type:
                permissions[row["pk"]] = [fields.get("codename"), *content_type]

    return content_types, permissions


def _remap(value, keys: dict, what: str, label: str):
    """A reference by id as its natural key; one by name stays."""
    if value is None or isinstance(value, list):
        return value, False

    natural = keys.get(value)

    if natural is None and isinstance(value, str) and value.isdigit():
        natural = keys.get(int(value))

    if natural is None:
        raise FixtureError(
            f"A {label} row refers to {what} {value}, which the file does "
            f"not hold. Make the file with dumpdata --natural-foreign, or "
            f"include {what}s in it."
        )

    return natural, True


def prepare(rows: list) -> Fixture:
    """
    Leave out the rows a restore never loads and rewrite references to
    content types and permissions as natural keys.
    """
    from django.contrib.contenttypes.models import ContentType

    try:
        from django.contrib.auth.models import Permission
    except (LookupError, RuntimeError):  # auth not installed
        Permission = None

    content_types, permissions = _natural_keys(rows)
    fixture = Fixture(rows=[])
    counts: Counter = Counter()
    unknown = set()

    for row in rows:
        label = row["model"]

        if is_skipped(label):
            fixture.skipped += 1
            continue

        try:
            model = apps.get_model(label)
        except (LookupError, ValueError):
            unknown.add(label)
            continue

        fields = row.get("fields") or {}

        for model_field in model._meta.get_fields():
            # Fields of the model itself (many-to-many included, which
            # have no column), not relations from other models.
            if model_field.auto_created and not model_field.concrete:
                continue

            if model_field.name not in fields:
                continue

            related = model_field.related_model

            if related is ContentType:
                keys, what = content_types, "content type"
            elif Permission is not None and related is Permission:
                keys, what = permissions, "permission"
            else:
                continue

            value = fields[model_field.name]

            if isinstance(model_field, models.ManyToManyField):
                remapped = []

                for item in value or []:
                    natural, changed = _remap(item, keys, what, label)
                    remapped.append(natural)
                    fixture.remapped += changed

                fields[model_field.name] = remapped
            else:
                natural, changed = _remap(value, keys, what, label)
                fields[model_field.name] = natural
                fixture.remapped += changed

        fixture.rows.append(row)
        counts[model._meta.label] += 1

    fixture.counts = dict(counts.most_common())
    fixture.unknown_models = sorted(unknown)
    return fixture


def load(path: str) -> Fixture:
    """Read and prepare the fixture at path."""
    return prepare(read_fixture(path))
