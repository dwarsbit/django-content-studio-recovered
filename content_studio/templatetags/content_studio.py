from django import template
from django.utils.safestring import mark_safe

from ..blocks import BlockList, BoundBlock

register = template.Library()


@register.simple_tag(takes_context=True)
def render_blocks(context, blocks):
    """
    Renders the blocks of a BlockField, each with its block's template:

        {% load content_studio %}
        {% render_blocks page.sections %}

    Also takes a list of blocks from BlockList.blocks, such as a slice.
    """
    if isinstance(blocks, BlockList):
        blocks = blocks.blocks
    elif blocks in (None, ""):
        return ""
    elif not all(isinstance(block, BoundBlock) for block in blocks):
        raise TypeError("render_blocks takes the value of a BlockField.")

    engine = context.template.engine
    rendered = []

    for block in blocks:
        block_template = engine.get_template(block.block.get_template_name())

        with context.push(**block.block.get_context(block)):
            rendered.append(block_template.render(context))

    return mark_safe("".join(rendered))


@register.simple_tag
def image_size(item, name):
    """
    One size (IMAGE_SIZES) of a media library image: a dict of url,
    width, height and ready, or None for an unknown size or an item that
    is not an image:

        {% image_size page.cover "card" as card %}
        <img src="{{ card.url }}" width="{{ card.width }}" height="{{ card.height }}">

    A size that is not made yet is the image's own file.
    """
    from ..media_library.sizes import get_image_sizes

    if not item:
        return None

    return get_image_sizes(item).get(name)


@register.simple_tag
def image_url(item, name):
    """
    The URL of one size of a media library image, or "" when there is
    none: {% image_url page.cover "hero" %}.
    """
    size = image_size(item, name)

    return size["url"] if size else ""


@register.filter
def rich_text(value):
    """
    Renders rich text: sanitized with the site's HTML sanitizer
    (HTML_SANITIZER, or the built-in allowlist), with the URLs of media
    library images and of links to other objects brought up to date:

        {% load content_studio %}
        {{ article.body|rich_text }}

    A link to an object that is gone keeps its text without the link.
    """
    from ..rich_text import render_rich_text
    from ..sanitizers import get_default_sanitizer

    if not value:
        return ""

    return mark_safe(render_rich_text(get_default_sanitizer()(str(value))))


@register.simple_tag(takes_context=True)
def preview_banner(context):
    """
    A thin bar at the top of a page opened with a preview link, saying
    it shows a draft that is not public (with an Edit link for a staff
    preview). Renders nothing on other requests, and on the live page.
    Needs the request in the context (the request context processor).

        {% load content_studio %}
        <body>{% preview_banner %} ...
    """
    from django.template.loader import render_to_string
    from django.urls import NoReverseMatch, reverse

    from ..previews import STAFF, get_preview, get_studio, is_live

    request = context.get("request")

    if request is None:
        return ""

    preview = get_preview(request)

    if preview is None:
        return ""

    obj = preview.get_object()
    studio = get_studio(preview.model)

    if obj is None or studio is None or is_live(studio, obj):
        return ""

    edit_url = None

    if preview.kind == STAFF:
        try:
            edit_url = (
                f"{reverse('content_studio_web')}content/"
                f"{preview.model._meta.label_lower}/{preview.pk}"
            )
        except NoReverseMatch:  # pragma: no cover - admin not mounted
            edit_url = None

    return render_to_string(
        "content_studio/previews/banner.html",
        {"preview": preview, "edit_url": edit_url, "staff": preview.kind == STAFF},
        request=request,
    )
