"""
File types that are never uploaded: those a browser runs when the file is
opened from the site, whatever upload setting allows.

A web server picks a file's Content-Type from its extension. HTML, XHTML,
SVG and every other XML type can carry scripts that run with the site's
privileges when the file is opened from MEDIA_URL on the admin's domain;
scripts and style sheets can be pulled into such a page. The type is
looked up the way a web server does (Python's mimetypes table, which
follows the common mime.types), with a fixed list on top for extensions
the table may not know.
"""

import mimetypes
import posixpath

# Extensions always refused, whatever mimetypes says about them.
ACTIVE_EXTENSIONS = frozenset(
    {
        # HTML and server-side includes.
        "htm",
        "html",
        "shtm",
        "shtml",
        "xht",
        "xhtml",
        "mht",
        "mhtml",
        # SVG and other XML that browsers render as documents.
        "svg",
        "svgz",
        "xml",
        "xsl",
        "xslt",
        "xsd",
        "rdf",
        "rss",
        "atom",
        "mathml",
        "mml",
        "xbl",
        "xul",
        # Scripts, style sheets and plug-ins.
        "js",
        "mjs",
        "cjs",
        "css",
        "swf",
        "jar",
        "jnlp",
        "hta",
        "wasm",
        "appcache",
        "manifest",
        "webmanifest",
    }
)


def _base(name: str) -> str:
    # Trailing dots and spaces are dropped by some file systems and
    # servers ("page.html." is then "page.html").
    return posixpath.basename((name or "").replace("\\", "/")).rstrip(". ")


def extension_of(name: str) -> str:
    """The file's extension, lowercase, without the dot."""
    base = _base(name)
    return base.rsplit(".", 1)[-1].lower().strip() if "." in base else ""


def _extensions(name: str) -> list[str]:
    """Every extension of a name: "a.html.gz" has "html" and "gz"."""
    return [part.lower().strip() for part in _base(name).split(".")[1:]]


def is_active_type(content_type: str) -> bool:
    content_type = (content_type or "").lower()
    main = content_type.split(";", 1)[0].strip()

    return (
        main in ("text/html", "application/xhtml+xml", "text/css", "image/svg+xml")
        or main in ("text/xml", "application/xml", "text/xsl")
        or main.endswith("+xml")
        or "javascript" in main
        or "ecmascript" in main
        or main == "application/wasm"
        or main == "application/x-shockwave-flash"
    )


def is_active_file(name: str) -> bool:
    """
    Whether a file by this name could be served as a type a browser runs
    or renders as a document (HTML, SVG, XML, script, style sheet). Every
    extension counts, not only the last: Apache serves "page.html.gz" as
    HTML, and "page.html.x" too when it does not know "x".
    """
    for extension in _extensions(name):
        if extension in ACTIVE_EXTENSIONS:
            return True

        content_type, _encoding = mimetypes.guess_type(f"file.{extension}")

        if content_type is not None and is_active_type(content_type):
            return True

    return False
