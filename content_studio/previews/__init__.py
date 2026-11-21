"""
Previews: links to an object's page on the site that also show it while it
is not live.

A preview link is the studio's page URL for the object (its
get_view_on_site_url, per content language) with a token in a query
parameter (PREVIEW_PARAM, "preview"). There are two kinds of token:

- a staff preview, made when an editor clicks Preview or Copy preview
  link: signed with SECRET_KEY, it names the object, the language and the
  editor, and works for PREVIEW_MAX_AGE seconds (an hour). The editor's
  view permission is checked again when it is opened.
- a shared draft link, made in the Share draft link dialog: a random key,
  stored hashed in a PreviewLink row of the optional content_studio.previews
  app, with an expiry date (or none), until it is revoked.

The site honours a token with get_preview(request), or previewable() in a
view: the live objects of a queryset plus the previewed one.

Live content never gets a token: its links are the plain URL.

This module works without the app installed (staff previews only), so it
imports the model lazily.
"""

from __future__ import annotations

import hashlib
import secrets
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.apps import apps as django_apps
from django.core import signing
from django.utils import timezone, translation

from ..settings import cs_settings

if TYPE_CHECKING:  # pragma: no cover
    from .models import PreviewLink

__all__ = [
    "Preview",
    "get_preview",
    "previewable",
]

STAFF = "staff"
SHARED = "shared"

# Signed tokens of staff previews; the salt keeps them apart from every
# other signed value of the project.
SALT = "content_studio.previews.staff"


def links_installed() -> bool:
    """Whether shared draft links are available (the app is installed)."""
    return django_apps.is_installed("content_studio.previews")


def get_param() -> str:
    return cs_settings.PREVIEW_PARAM or "preview"


@dataclass
class Preview:
    """
    What a request's preview token gives access to: one object of one
    model, in a language (None: the site's own), until expires_at.
    """

    model: type
    pk: str
    language: Optional[str]
    kind: str  # "staff" or "shared"
    # Who made the link: the editor of a staff preview, the creator of a
    # shared link (None once that user is deleted).
    user: Any
    expires_at: Optional[datetime]
    # The stored link of a shared preview.
    link: Optional["PreviewLink"] = None

    def matches(self, model_or_obj) -> bool:
        """Whether the token is for this model (or this object)."""
        model = model_or_obj if isinstance(model_or_obj, type) else type(model_or_obj)

        if model._meta.concrete_model is not self.model._meta.concrete_model:
            return False

        return isinstance(model_or_obj, type) or str(model_or_obj.pk) == self.pk

    def get_object(self):
        """The previewed object, or None when it no longer exists."""
        return self.model._default_manager.filter(pk=self.pk).first()

    @property
    def shared_by(self) -> str:
        if self.user is None:
            return ""

        return self.user.get_full_name() or self.user.get_username()


# Tokens ------------------------------------------------------------------


def make_staff_token(user, obj, language: Optional[str] = None) -> str:
    return signing.dumps(
        {
            "m": obj._meta.label_lower,
            "p": str(obj.pk),
            "l": language or None,
            "u": user.pk,
        },
        salt=SALT,
        compress=True,
    )


def new_key() -> str:
    """A shared link's key: 32 random bytes, URL safe (no ":", unlike a
    signed staff token)."""
    return secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def with_token(url: str, token: str) -> str:
    """url with the preview parameter set to token (replacing one)."""
    param = get_param()
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    query = [(k, v) for k, v in query if k != param] + [(param, token)]

    return urlunsplit(parts._replace(query=urlencode(query)))


# The studio side -----------------------------------------------------------


def get_studio(model):
    return cs_settings.ADMIN_SITE._registry.get(model._meta.concrete_model) or (
        cs_settings.ADMIN_SITE._registry.get(model)
    )


def preview_enabled(studio) -> bool:
    """Whether the studio previews content that is not live: it has
    publishing, and preview is not turned off."""
    from ..publishing import get_publishing

    return bool(getattr(studio, "preview", True)) and get_publishing(studio) is not None


def is_live(studio, obj, now=None) -> bool:
    """Whether obj is live: published, or its studio has no publishing."""
    from ..publishing import PUBLISHED, get_publishing, get_state

    config = get_publishing(studio)

    return config is None or get_state(config, obj, now) == PUBLISHED


def page_url(studio, obj, language: Optional[str] = None) -> Optional[str]:
    """
    The studio's page URL for obj (get_view_on_site_url), in a content
    language: the hook runs with that language active, so reverse() with
    i18n_patterns gives the language's URL. None without a page, or for
    a URL that is not http(s), mailto or relative.
    """
    from ..utils import safe_link_url

    with translation.override(language) if language else nullcontext():
        url = studio.get_view_on_site_url(obj)

    return safe_link_url(url) if url else None


def preview_url(studio, obj, user, language: Optional[str] = None) -> Optional[str]:
    """
    The link of Preview and Copy preview link: the page URL, with a staff
    token when obj is not live. None without a page URL.
    """
    url = page_url(studio, obj, language)

    if url is None or is_live(studio, obj):
        return url

    return with_token(url, make_staff_token(user, obj, language))


# Shared links -------------------------------------------------------------


def share(
    studio,
    obj,
    user,
    *,
    expires_at: Optional[datetime],
    language: Optional[str] = None,
    note: str = "",
) -> tuple["PreviewLink", str]:
    """
    Create a shared draft link for obj. Returns the link and its key: the
    key is shown once, only its hash is stored.
    """
    from django.contrib.contenttypes.models import ContentType

    from .models import PreviewLink

    key = new_key()
    link = PreviewLink.objects.create(
        content_type=ContentType.objects.get_for_model(obj, for_concrete_model=False),
        object_id=str(obj.pk),
        language=language or "",
        key_hash=hash_key(key),
        note=note[:200],
        created_by=user,
        expires_at=expires_at,
    )

    return link, key


def active_links(obj):
    """The shared links of obj that still work, newest first."""
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q

    from .models import PreviewLink

    return (
        PreviewLink.objects.filter(
            content_type=ContentType.objects.get_for_model(
                obj, for_concrete_model=False
            ),
            object_id=str(obj.pk),
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .select_related("created_by")
        .order_by("-created_at", "-pk")
    )


# The site side ----------------------------------------------------------------


class _AsUser:
    """The request, as the user who made a staff token: the studio's
    permission checks read request.user."""

    def __init__(self, request, user):
        self._request = request
        self.user = user

    def __getattr__(self, name):
        return getattr(self._request, name)


def _load_staff(request, token) -> Optional[Preview]:
    try:
        data = signing.loads(token, salt=SALT, max_age=cs_settings.PREVIEW_MAX_AGE or 0)
    except signing.BadSignature:
        return None

    try:
        model = django_apps.get_model(data["m"])
    except (KeyError, LookupError, ValueError):
        return None

    from django.contrib.auth import get_user_model

    user = get_user_model()._default_manager.filter(pk=data.get("u")).first()
    studio = get_studio(model)

    # The editor may still see the model: a removed editor's links stop.
    if (
        user is None
        or not user.is_active
        or studio is None
        or not studio.has_view_permission(_AsUser(request, user))
    ):
        return None

    return Preview(
        model=model,
        pk=str(data["p"]),
        language=data.get("l") or None,
        kind=STAFF,
        user=user,
        expires_at=_staff_expiry(token),
    )


def _staff_expiry(token: str) -> Optional[datetime]:
    """When a verified staff token stops working: the time it was signed
    (the middle part of value:timestamp:signature) plus the max age."""
    try:
        signed_at = signing.b62_decode(token.rsplit(":", 2)[1])
    except (IndexError, ValueError):  # pragma: no cover - verified already
        return None

    return datetime.fromtimestamp(signed_at, tz=dt_timezone.utc) + timedelta(
        seconds=cs_settings.PREVIEW_MAX_AGE or 0
    )


def _load_shared(token) -> Optional[Preview]:
    if not links_installed():
        return None

    from django.db.models import F

    from .models import PreviewLink

    link = (
        PreviewLink.objects.filter(key_hash=hash_key(token))
        .select_related("content_type", "created_by")
        .first()
    )

    if link is None or (link.expires_at and link.expires_at <= timezone.now()):
        return None

    model = link.content_type.model_class()

    if model is None:
        return None

    now = timezone.now()
    PreviewLink.objects.filter(pk=link.pk).update(
        opens=F("opens") + 1, last_opened_at=now
    )

    return Preview(
        model=model,
        pk=link.object_id,
        language=link.language or None,
        kind=SHARED,
        user=link.created_by,
        expires_at=link.expires_at,
        link=link,
    )


def get_preview(request) -> Optional[Preview]:
    """
    The preview the request's token gives (the PREVIEW_PARAM query
    parameter), or None without a token or for one that does not work
    (expired, revoked, tampered with). The result is kept on the request,
    so a shared link's opening is counted once.
    """
    cached = getattr(request, "_content_studio_preview", False)

    if cached is not False:
        return cached

    token = (getattr(request, "GET", None) or {}).get(get_param()) or ""
    preview = None

    if 0 < len(token) <= 2048:
        preview = _load_staff(request, token) if ":" in token else _load_shared(token)

    try:
        request._content_studio_preview = preview
    except AttributeError:  # pragma: no cover - a read-only request object
        pass

    return preview


def previewable(request, queryset, publishing=None):
    """
    The objects of queryset the request may see on the site: the live
    ones, plus the object the request previews.

        article = get_object_or_404(
            previewable(request, Article.objects.all()), slug=slug
        )

    publishing is the studio's Publishing, a field name or a studio; by
    default the publishing of the model's registered studio. A model
    without publishing is live as a whole: the queryset is returned as
    it is.
    """
    from ..publishing import get_publishing, live

    if publishing is None:
        studio = get_studio(queryset.model)
        publishing = get_publishing(studio) if studio is not None else None

        if publishing is None:
            return queryset

    result = live(queryset, publishing)
    preview = get_preview(request)

    if preview is None or not preview.matches(queryset.model):
        return result

    return result | queryset.filter(pk=preview.pk)


def default_expiry(days: Optional[int] = 7) -> Optional[datetime]:
    return timezone.now() + timedelta(days=days) if days else None
