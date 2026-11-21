"""
Previews and shared draft links (MOCKUP SPIKE, not for merge).

A preview link is the object's page URL (the studio's
get_view_on_site_url) with a ?preview=<token> parameter. Staff tokens
are signed and last an hour; shared draft links are kept here in
memory for the mockups (the real build stores them in the optional
content_studio.previews app).
"""

import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from django.apps import apps
from django.core import signing
from django.utils import timezone

PARAM = "preview"
SALT = "content_studio.preview"
STAFF_MAX_AGE = 60 * 60

# key -> SharedLink, for the mockups only.
_LINKS: dict[str, "SharedLink"] = {}


@dataclass
class SharedLink:
    id: str
    key: str
    model: str
    pk: str
    language: Optional[str]
    note: str
    created_by: str
    created_at: Any
    expires_at: Any
    opens: int = 0
    last_opened_at: Any = None


@dataclass
class Preview:
    model: str
    pk: str
    language: Optional[str]
    kind: str  # "staff" or "shared"
    expires_at: Any = None
    shared_by: Optional[str] = None
    extra: dict = field(default_factory=dict)


def with_token(url: str, token: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != PARAM]
    query.append((PARAM, token))
    return urlunsplit(parts._replace(query=urlencode(query)))


def staff_token(user, obj, language=None) -> str:
    return signing.dumps(
        {"m": obj._meta.label_lower, "pk": str(obj.pk), "l": language, "u": user.pk},
        salt=SALT,
        compress=True,
    )


def share(user, obj, language=None, days: Optional[int] = 7, note="") -> SharedLink:
    now = timezone.now()
    link = SharedLink(
        id=secrets.token_hex(4),
        key=secrets.token_urlsafe(24),
        model=obj._meta.label_lower,
        pk=str(obj.pk),
        language=language,
        note=note,
        created_by=user.get_full_name() or user.get_username(),
        created_at=now,
        expires_at=now + timedelta(days=days) if days else None,
    )
    _LINKS[link.key] = link
    return link


def links_for(obj) -> list[SharedLink]:
    label = obj._meta.label_lower
    now = timezone.now()
    return sorted(
        (
            link
            for link in _LINKS.values()
            if link.model == label
            and link.pk == str(obj.pk)
            and (link.expires_at is None or link.expires_at > now)
        ),
        key=lambda link: link.created_at,
        reverse=True,
    )


def revoke(obj, link_id: str) -> bool:
    for key, link in list(_LINKS.items()):
        if link.id == link_id and link.pk == str(obj.pk):
            del _LINKS[key]
            return True
    return False


def get_preview(request) -> Optional[Preview]:
    """The preview a request's ?preview= token gives, or None."""
    token = request.GET.get(PARAM)

    if not token:
        return None

    link = _LINKS.get(token)

    if link is not None:
        if link.expires_at is not None and link.expires_at <= timezone.now():
            return None
        link.opens += 1
        link.last_opened_at = timezone.now()
        return Preview(
            link.model,
            link.pk,
            link.language,
            "shared",
            expires_at=link.expires_at,
            shared_by=link.created_by,
        )

    try:
        data = signing.loads(token, salt=SALT, max_age=STAFF_MAX_AGE)
    except signing.BadSignature:
        return None

    return Preview(
        data["m"],
        data["pk"],
        data.get("l"),
        "staff",
        expires_at=None,
    )


def previewable(request, queryset, publishing="published_at"):
    """live(queryset) plus the object the request previews, if any."""
    from .publishing import live

    preview = get_preview(request)
    request.content_studio_preview = preview
    result = live(queryset, publishing)

    if preview is None or preview.model != queryset.model._meta.label_lower:
        return result

    return queryset.filter(pk=preview.pk) | result


def is_model(preview, model) -> bool:
    return preview is not None and preview.model == model._meta.label_lower


def model_for(label):
    return apps.get_model(label)
