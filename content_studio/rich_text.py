"""
Rich text references: images from the media library and links to other
objects, kept up to date when the HTML is rendered.

The rich text editor stores the URL at the time of editing and, next to
it, what the URL points at:

    <img src="/media/blue-ridge.jpg" data-media-id="7" data-size="hero">
    <a href="/stories/last-ferry/" data-link-model="blog.article"
       data-link-id="12">

The HTML works as stored. render_rich_text() (and the rich_text template
filter) replaces those URLs with the current ones, so a replaced file, a
new crop or a changed slug never leaves a broken image or link. Only
models with a studio that rich text can link to are resolved, and saving
checks that the editor may see each object a new link points at
(check_links), so a link never reveals the URL of an object they cannot.
"""

import html
import logging
from collections import defaultdict
from html.parser import HTMLParser
from typing import Optional

from django.apps import apps
from django.utils.translation import gettext as _

from .settings import cs_settings

__all__ = ["render_rich_text"]

logger = logging.getLogger(__name__)

# The image's own file instead of one of IMAGE_SIZES.
ORIGINAL_SIZE = "original"


def get_link_url(studio, obj) -> Optional[str]:
    """
    The URL a rich text link to obj gets: its studio's get_link_url, or
    obj.get_absolute_url() for a model without a studio. None when obj
    has no URL or computing it fails.
    """
    try:
        if studio is not None:
            return studio.get_link_url(obj) or None

        get_absolute_url = getattr(obj, "get_absolute_url", None)

        return get_absolute_url() if callable(get_absolute_url) else None
    except Exception:
        logger.exception("Could not get the URL of %r for a rich text link.", obj)
        return None


def get_image_src(item, size: str) -> dict:
    """
    The src, width and height of a media library image in a size of
    IMAGE_SIZES, or of the image's own file for "original" or a size
    that does not exist (anymore).
    """
    from .media_library.metadata import get_metadata_attr
    from .media_library.sizes import get_image_sizes

    if size != ORIGINAL_SIZE:
        entry = get_image_sizes(item).get(size)

        if entry:
            return {
                "src": entry["url"],
                "width": entry.get("width"),
                "height": entry.get("height"),
            }

    attr = get_metadata_attr()
    metadata = (getattr(item, attr, None) or {}) if attr else {}

    return {
        "src": item.file.url,
        "width": metadata.get("width"),
        "height": metadata.get("height"),
    }


class _ReferenceCollector(HTMLParser):
    """Collects the media ids and linked objects in rich text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.media_ids = set()
        self.links = defaultdict(set)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "img" and attrs.get("data-media-id"):
            self.media_ids.add(attrs["data-media-id"])

        if tag == "a" and attrs.get("data-link-model") and attrs.get("data-link-id"):
            self.links[attrs["data-link-model"].lower()].add(attrs["data-link-id"])

    handle_startendtag = handle_starttag


class _ReferenceRewriter(HTMLParser):
    """
    Writes the HTML back out unchanged, except for the src of media
    library images and the href of links to objects. A link to an object
    that is gone (or has no URL anymore) keeps its text and loses the
    link.
    """

    def __init__(self, images: dict, links: dict):
        super().__init__(convert_charrefs=False)
        self.images = images
        self.links = links
        self.out = []
        # Per open <a>: whether its tag was dropped.
        self.anchors = []

    def result(self) -> str:
        return "".join(self.out)

    def _tag(self, tag, attrs, closed=False) -> str:
        parts = [tag]

        for name, value in attrs:
            if value is None:
                parts.append(name)
            else:
                parts.append(f'{name}="{html.escape(str(value), quote=True)}"')

        return "<" + " ".join(parts) + (" />" if closed else ">")

    def _image(self, attrs, closed):
        values = dict(attrs)
        item = self.images.get(values.get("data-media-id"))

        if item is None:
            return self.get_starttag_text()

        current = get_image_src(item, values.get("data-size") or ORIGINAL_SIZE)
        updated = {"src": current["src"]}

        if current["width"] and current["height"]:
            updated["width"] = current["width"]
            updated["height"] = current["height"]

        attrs = [
            (name, updated.pop(name) if name in updated else value)
            for name, value in attrs
        ] + list(updated.items())

        return self._tag("img", attrs, closed)

    def handle_starttag(self, tag, attrs, closed=False):
        if tag == "img":
            self.out.append(self._image(attrs, closed))
            return

        if tag == "a":
            values = dict(attrs)
            model = (values.get("data-link-model") or "").lower()
            object_id = values.get("data-link-id")

            if model and object_id and model in self.links:
                url = self.links[model].get(object_id)

                if url is None:
                    # The object is gone, or has no URL: keep the text.
                    self.anchors.append(True)
                    return

                attrs = [
                    (name, url if name == "href" else value) for name, value in attrs
                ]

                if "href" not in values:
                    attrs.append(("href", url))

                self.anchors.append(False)
                self.out.append(self._tag("a", attrs))
                return

            self.anchors.append(False)

        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            self.out.append(self._image(attrs, True))
        else:
            self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "a" and self.anchors and self.anchors.pop():
            return

        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        self.out.append(f"<?{data}>")

    def unknown_decl(self, data):
        self.out.append(f"<![{data}]>")


def _load_images(media_ids) -> dict:
    media_model = cs_settings.MEDIA_LIBRARY_MODEL

    if media_model is None or not media_ids:
        return {}

    pk_field = media_model._meta.pk
    ids = []

    for media_id in media_ids:
        try:
            ids.append(pk_field.to_python(media_id))
        except Exception:
            continue

    return {str(item.pk): item for item in media_model.objects.filter(pk__in=ids)}


def _linkable_studio(label: str):
    """The studio of a model rich text links may point to, else None."""
    from .admin import is_linkable

    site = cs_settings.ADMIN_SITE
    registry = getattr(site, "_registry", {}) if site else {}

    try:
        model = apps.get_model(label)
    except (LookupError, ValueError):
        return None

    studio = registry.get(model)

    return studio if studio is not None and is_linkable(studio) else None


def _load_links(links: dict) -> dict:
    """
    The current URL of every linked object, per model label and id; None
    for an object that is gone, trashed or has no URL. Models without a
    studio that can be linked to are left out, so their links stay as
    they are.
    """
    urls = {}

    for label, object_ids in links.items():
        studio = _linkable_studio(label)

        if studio is None:
            continue

        model = studio.model
        pk_field = model._meta.pk
        ids = []

        for object_id in object_ids:
            try:
                ids.append(pk_field.to_python(object_id))
            except Exception:
                continue

        queryset = model._default_manager.filter(pk__in=ids)
        soft_delete = getattr(studio, "soft_delete", "")

        if soft_delete:
            queryset = queryset.filter(**{f"{soft_delete}__isnull": True})

        found = {str(obj.pk): get_link_url(studio, obj) for obj in queryset}
        urls[label] = {
            str(object_id): found.get(str(object_id)) for object_id in object_ids
        }

    return urls


def collect_links(value) -> dict:
    """The linked objects in rich text (or in a JSON value holding it)."""
    links: dict = defaultdict(set)

    def visit(item):
        if isinstance(item, str):
            if "data-link-model" in item:
                collector = _ReferenceCollector()
                collector.feed(item)
                collector.close()

                for label, ids in collector.links.items():
                    links[label] |= ids
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return links


def check_links(request, value, previous=None) -> list[str]:
    """
    The errors of the links rich text gains (those not already in
    previous): each must point at a model rich text can link to, which
    the editor may view, and at an object of it they can see (their
    tenant, the studio's get_queryset). A link to an object that no
    longer exists is left alone: rendering drops it.
    """
    from .utils import get_tenant_scoped_queryset

    links = collect_links(value)
    known = collect_links(previous) if previous is not None else {}
    errors = []

    for label, object_ids in links.items():
        new_ids = object_ids - known.get(label, set())

        if not new_ids:
            continue

        studio = _linkable_studio(label)

        if studio is None or not studio.has_view_permission(request):
            errors.append(_("A link points to something you cannot link to."))
            continue

        model = studio.model
        pk_field = model._meta.pk
        ids = []

        for object_id in new_ids:
            try:
                ids.append(pk_field.to_python(object_id))
            except Exception:
                continue

        visible = set(
            str(pk)
            for pk in get_tenant_scoped_queryset(
                request, model, studio.get_queryset(request)
            )
            .filter(pk__in=ids)
            .values_list("pk", flat=True)
        )
        existing = set(
            str(pk)
            for pk in model._default_manager.filter(pk__in=ids).values_list(
                "pk", flat=True
            )
        )

        if existing - visible:
            errors.append(_("A link points to something you cannot link to."))

    return errors


def render_rich_text(value: Optional[str]) -> str:
    """
    Rich text with its references brought up to date: media library
    images get the current URL (and width and height) of their size,
    links to objects the object's current URL, and a link to an object
    that is gone keeps its text without the link. Everything else is
    left as it is, so it does not sanitize; the rich_text template
    filter does both. Takes one query per media model and per linked
    model.
    """
    if not value:
        return value or ""

    if "data-media-id" not in value and "data-link-model" not in value:
        return value

    collector = _ReferenceCollector()
    collector.feed(value)
    collector.close()

    rewriter = _ReferenceRewriter(
        images=_load_images(collector.media_ids),
        links=_load_links(collector.links),
    )
    rewriter.feed(value)
    rewriter.close()

    return rewriter.result()
