from typing import TYPE_CHECKING

__title__ = "Django Content Studio"
__version__ = "1.21.2"
__author__ = "Leon van der Grient"
__license__ = "MIT"

# Version synonym
VERSION = __version__

# The documented entry point (`from content_studio import register`) is
# resolved lazily: importing the admin module eagerly would require the
# app registry to be ready.
__all__ = ["VERSION", "register"]

# Type checkers see the import itself.
if TYPE_CHECKING:
    from .admin import register


def __getattr__(name):
    if name == "register":
        from . import admin

        return getattr(admin, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
