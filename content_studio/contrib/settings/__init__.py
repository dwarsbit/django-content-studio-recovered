"""
Settings from environment variables, so a project runs from its
environment (or a .env file its process manager loads) alone.

Call configure() near the top of the project's settings module::

    # config/settings.py
    from pathlib import Path

    from content_studio.contrib.settings import configure

    BASE_DIR = Path(__file__).resolve().parent.parent

    CONTENT_STUDIO = {"ADMIN_SITE": "config.studio.admin_site"}
    configure(globals(), base_dir=BASE_DIR)

    INSTALLED_APPS = [
        ...
        "content_studio.contrib.settings",
    ]

Settings assigned after the call override it. The CONTENT_STUDIO,
REST_FRAMEWORK and HEADLESS dictionaries assigned before the call are
merged over the defaults, one level deep: a key you set replaces the
default's value whole.

Installing the app adds the deploy checks and creates the tables of a
db:// cache and a db:// task queue after migrate.

configure() runs the sections in sections.SECTIONS, then the project's
own (``sections=[...]``). See the environment settings docs for every
variable and its default.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .env import Env
from .sections import (
    DEFAULT_PROJECT_NAME,
    DEFAULT_SITE_URL,
    SECTIONS,
    Context,
    Section,
)

__all__ = [
    "Context",
    "Env",
    "Section",
    "configure",
]

# Dictionary settings that sections add keys to, and that the project's
# own dictionary (assigned before configure()) is merged over.
MERGED_SETTINGS = ("CONTENT_STUDIO", "REST_FRAMEWORK", "HEADLESS")


def _merge(defaults: Mapping[str, Any], overrides: Any) -> dict[str, Any]:
    merged = dict(defaults)

    if isinstance(overrides, Mapping):
        merged.update(overrides)

    return merged


def configure(
    namespace: MutableMapping[str, Any],
    *,
    base_dir: Path | str,
    env: Mapping[str, str] | None = None,
    sections: Iterable[Section] = (),
) -> MutableMapping[str, Any]:
    """
    Set the environment-driven settings in ``namespace`` (a settings
    module's ``globals()``) and return it. ``env`` defaults to
    ``os.environ``; ``sections`` run after the built-in ones.
    """
    e = Env(os.environ if env is None else env)
    base_dir = Path(base_dir)
    site_url = (e.str("SITE_URL") or DEFAULT_SITE_URL).rstrip("/")
    settings: dict[str, Any] = {}

    base = {
        "env": e,
        "base_dir": base_dir,
        "namespace": MappingProxyType(dict(namespace)),
        "debug": e.bool("DJANGO_DEBUG", False),
        "project_name": e.str("PROJECT_NAME") or DEFAULT_PROJECT_NAME,
        "site_url": site_url,
        "backend_url": (e.str("BACKEND_URL") or site_url).rstrip("/"),
    }

    for section in [*SECTIONS, *sections]:
        context = Context(settings=MappingProxyType(settings), **base)

        for name, value in section(context).items():
            current = settings.get(name)

            if name in MERGED_SETTINGS and isinstance(current, Mapping):
                settings[name] = _merge(current, value)
            else:
                settings[name] = value

    for name in MERGED_SETTINGS:
        if name in settings:
            settings[name] = _merge(settings[name], namespace.get(name))

    namespace.update(settings)
    return namespace
