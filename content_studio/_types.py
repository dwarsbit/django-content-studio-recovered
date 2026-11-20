"""
Type aliases shared by the hints of the public API. Not public
themselves: they only spell out what the hints accept.
"""

from typing import Union

from django.utils.functional import Promise

# Text shown to editors: a plain string or a lazy translation
# (gettext_lazy), which django-stubs types as a Promise.
StrOrPromise = Union[str, Promise]
