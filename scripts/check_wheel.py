"""
Verify the built wheel ships what users need: the compiled frontend
assets, the compiled translation catalogs and the py.typed marker.

Run after `poetry build`:

    python scripts/check_wheel.py
"""

import glob
import sys
import zipfile


def main():
    wheels = glob.glob("dist/*.whl")

    problems = []

    if not wheels:
        problems.append("no wheel found in dist/ — run `poetry build` first")
        wheels = []

    for wheel in wheels:
        names = zipfile.ZipFile(wheel).namelist()

        required = {
            "content_studio/static/content_studio/assets/": (
                "compiled frontend assets (run `npm run build` first)"
            ),
            **{
                f"content_studio/locale/{locale}/LC_MESSAGES/django.mo": (
                    f"the compiled {locale} translation catalog"
                )
                for locale in ("de", "es", "fr", "it", "nl", "pt_BR")
            },
            **{
                f"content_studio/static/content_studio/locales/{locale}/translation.json": (
                    f"the {locale} frontend translations"
                )
                for locale in ("en", "de", "es", "fr", "it", "nl", "pt-BR")
            },
            "content_studio/viewsets.py": ("the python package itself"),
            "content_studio/contrib/captcha/solver.wasm": (
                "the captcha's vendored solver"
            ),
            "content_studio/contrib/captcha/static/content_studio/captcha/cap.min.js": (
                "the captcha's vendored widget"
            ),
            "content_studio/contrib/captcha/NOTICE": (
                "the notice of the captcha's Apache-2.0 files"
            ),
            "content_studio/py.typed": (
                "the PEP 561 marker that lets type checkers use the hints"
            ),
        }

        for path, label in required.items():
            if not any(name.startswith(path) or name == path for name in names):
                problems.append(f"{wheel} is missing {label} ({path})")

    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        sys.exit(1)

    for wheel in wheels:
        print(f"OK: {wheel} contains the compiled assets, translations and py.typed")


if __name__ == "__main__":
    main()
