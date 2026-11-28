"""
Branding: the site's logo, favicon, accent color and login text, and the
environment badge.

The values live on the admin site (site_logo, site_logo_dark,
site_favicon, accent_color, accent_color_dark, login_text) and in the
ENVIRONMENT setting, which the site's get_environment(request) returns.
The admin page (index.html) renders the favicon, the browser tab's title
and the accent color's CSS variables, so they are right before the app
loads; the info endpoint sends the rest to the frontend.
"""

from typing import Any, Optional

from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

from .colors import normalize_color

# The badge's colors: the tones of the Badge component.
TONES = ("gray", "blue", "green", "yellow", "red", "purple")

# Environment names that need no dict, with their label and tone. A name
# mapped to None (production) shows no badge.
ENVIRONMENTS: dict[str, Optional[tuple[Any, str]]] = {
    "local": (_("Local"), "blue"),
    "development": (_("Development"), "blue"),
    "dev": (_("Development"), "blue"),
    "test": (_("Test"), "yellow"),
    "testing": (_("Test"), "yellow"),
    "staging": (_("Staging"), "yellow"),
    "acceptance": (_("Acceptance"), "yellow"),
    "production": None,
    "prod": None,
    "live": None,
}

# The page backgrounds the accent color is drawn on, as hex: the light
# theme's --background and the dark theme's (oklch(0.148 0.004 228.8)).
LIGHT_BACKGROUND = "#ffffff"
DARK_BACKGROUND = "#090b0c"

# The least contrast an accent color needs against the background, as for
# the focus ring and other non-text parts (WCAG 1.4.11).
MIN_ACCENT_CONTRAST = 3

# The static files a site's branding names.
ASSET_ATTRS = ("site_logo", "site_logo_dark", "site_favicon")


def environment_errors(value) -> list[str]:
    """Why an environment value cannot be shown, if it cannot."""
    if value is None or isinstance(value, str):
        return []

    if not isinstance(value, dict):
        return [
            "ENVIRONMENT must be None, a name or a dict with a label and a "
            f"color, not {value!r}."
        ]

    errors = []
    unknown = set(value) - {"label", "color"}

    if unknown:
        errors.append(
            "ENVIRONMENT has unknown keys: "
            + ", ".join(sorted(map(str, unknown)))
            + '; it takes "label" and "color".'
        )

    label = value.get("label")

    if not str(label or "").strip():
        errors.append('ENVIRONMENT needs a "label", the text of the badge.')

    color = value.get("color", "gray")

    if color not in TONES:
        errors.append(
            f"ENVIRONMENT's color must be one of {', '.join(TONES)}, " f"not {color!r}."
        )

    return errors


def resolve_environment(value) -> Optional[dict[str, str]]:
    """
    The badge of an environment value: {"label", "color"}, or None for no
    badge (None, an empty name, production, or a value that is not valid,
    which a system check reports).
    """
    if environment_errors(value):
        return None

    if isinstance(value, dict):
        return {"label": str(value["label"]), "color": value.get("color", "gray")}

    name = str(value or "").strip()

    if not name:
        return None

    if name.lower() in ENVIRONMENTS:
        known = ENVIRONMENTS[name.lower()]

        if known is None:
            return None

        label, color = known
        return {"label": str(label), "color": color}

    return {"label": name[:1].upper() + name[1:], "color": "gray"}


def get_environment(site, request) -> Optional[dict[str, str]]:
    """The badge the site shows for request, or None."""
    return resolve_environment(site.get_environment(request))


def _luminance(hex_color: str) -> float:
    """The relative luminance of a "#rrggbb" color (WCAG 2)."""

    def channel(value: int) -> float:
        value = value / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(first: str, second: str) -> float:
    """The contrast ratio of two "#rrggbb" colors, from 1 to 21."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def foreground_for(hex_color: str) -> str:
    """Black or white, whichever reads better on hex_color."""
    if contrast(hex_color, "#000000") >= contrast(hex_color, "#ffffff"):
        return "#000000"
    return "#ffffff"


def accent_errors(site) -> list[tuple[str, Any]]:
    """The accent colors of site that are not opaque CSS colors."""
    return [
        (attr, getattr(site, attr))
        for attr in ("accent_color", "accent_color_dark")
        if getattr(site, attr, None) not in (None, "")
        and normalize_color(getattr(site, attr), "hex") is None
    ]


def get_accent(site) -> Optional[dict[str, dict[str, str]]]:
    """
    The accent per theme, {"light": {"color", "foreground"}, "dark": ...}
    as "#rrggbb", or None without an accent color. accent_color_dark
    falls back to accent_color; a color that does not parse is left out
    (a system check reports it).
    """
    light = normalize_color(site.accent_color, "hex") if site.accent_color else None
    dark = (
        normalize_color(site.accent_color_dark, "hex")
        if site.accent_color_dark
        else None
    ) or light

    if light is None and dark is None:
        return None

    accent = {}

    for theme, color in (("light", light), ("dark", dark)):
        if color:
            accent[theme] = {"color": color, "foreground": foreground_for(color)}

    return accent


def accent_warnings(site) -> list[tuple[str, str, float]]:
    """
    The accent colors with too little contrast against their theme's
    background: (attribute, theme, contrast).
    """
    accent = get_accent(site)

    if accent is None:
        return []

    warnings = []

    for theme, background in (("light", LIGHT_BACKGROUND), ("dark", DARK_BACKGROUND)):
        if theme not in accent:
            continue

        ratio = contrast(accent[theme]["color"], background)

        if ratio < MIN_ACCENT_CONTRAST:
            attr = (
                "accent_color_dark"
                if theme == "dark" and site.accent_color_dark
                else "accent_color"
            )
            warnings.append((attr, theme, ratio))

    return warnings


def accent_css(site) -> str:
    """
    The CSS that puts the accent in the admin's color variables, for a
    <style> after its stylesheet; empty without an accent. The colors are
    canonical "#rrggbb", so nothing else reaches the page.
    """
    accent = get_accent(site)

    if accent is None:
        return ""

    rules = []

    for theme, selector in (("light", ":root"), ("dark", ":root.dark")):
        if theme not in accent:
            continue

        color = accent[theme]["color"]
        foreground = accent[theme]["foreground"]
        declarations = "".join(
            f"--{name}:{value};"
            for name, value in (
                ("primary", color),
                ("primary-foreground", foreground),
                ("ring", color),
                ("sidebar-primary", color),
                ("sidebar-primary-foreground", foreground),
                ("sidebar-ring", color),
            )
        )
        rules.append(f"{selector}{{{declarations}}}")

    return "".join(rules)


def is_url(path: str) -> bool:
    """Whether path is a URL or an absolute path rather than a static file."""
    return path.startswith(("http://", "https://", "//", "/", "data:"))


def asset_url(path: Optional[str]) -> Optional[str]:
    """
    The URL of a logo or favicon: a URL as it is, a static file path
    through the static files storage; None when there is none, or the
    storage's manifest does not have the file (a system check reports it).
    """
    path = str(path or "").strip()

    if not path:
        return None

    if is_url(path):
        return path

    try:
        return static(path)
    except ValueError:
        return None


def missing_static_files(site) -> list[tuple[str, str]]:
    """The logo and favicon paths of site that no static files finder has."""
    missing = []

    for attr in ASSET_ATTRS:
        path = str(getattr(site, attr, None) or "").strip()

        if path and not is_url(path) and not finders.find(path):
            missing.append((attr, path))

    return missing


def get_branding(site, request) -> dict[str, Any]:
    """What the frontend needs of the site's branding, for the info endpoint."""
    login_text = str(site.login_text or "").strip()

    return {
        "logo": asset_url(site.site_logo),
        "logo_dark": asset_url(site.site_logo_dark),
        "login_text": login_text or None,
        "environment": get_environment(site, request),
    }


def get_page_title(site, request) -> str:
    """The browser tab's title: site_title, after the environment's label."""
    title = str(site.site_title or "").strip() or "Django Content Studio"
    environment = get_environment(site, request)

    if environment:
        return f"[{environment['label']}] {title}"

    return title
