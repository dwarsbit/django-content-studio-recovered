import json
import re
import shutil
import tempfile
from pathlib import Path

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.management import call_command
from django.test import TestCase, override_settings

ENTRY_FILES = [
    "content_studio/img/favicon.png",
    "content_studio/assets/index.js",
    "content_studio/assets/index.css",
    "content_studio/fonts/inter/index.css",
    "content_studio/icons/pi/style.css",
]


class ManifestStaticFilesTests(TestCase):
    """
    The web app renders with a manifest storage in production (#108).
    """

    def setUp(self):
        # A manifest as collectstatic writes it for the files the page
        # references. Like a real one, it has no entry for the empty name.
        static_root = tempfile.mkdtemp(prefix="content_studio_static_")
        self.addCleanup(shutil.rmtree, static_root)
        paths = {name: name.replace(".", ".abc123.", 1) for name in ENTRY_FILES}
        manifest = {"paths": paths, "version": "1.1", "hash": "abc123"}
        Path(static_root, "staticfiles.json").write_text(json.dumps(manifest))

        settings = override_settings(
            DEBUG=False,
            STATIC_ROOT=static_root,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
                },
            },
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def test_index_renders(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'window.DCS_STATIC_PREFIX = "/static/content_studio/";'
        )
        self.assertContains(response, "/static/content_studio/assets/index.abc123.js")


class StrictManifestStaticFilesStorage(ManifestStaticFilesStorage):
    # Already Django's default; spelled out because it is what the test is
    # about: a name missing from the manifest raises instead of passing.
    manifest_strict = True


class CollectstaticTests(TestCase):
    """
    The web app renders with DEBUG off after a real collectstatic into a
    manifest storage, Django's own and WhiteNoise's compressed one. The
    storage hashes and rewrites every file it collects, so the page fails
    if a template asks for a name the manifest lacks, such as the empty
    name of {% static '' %}.
    """

    def setUp(self):
        # Stand-ins for the built frontend, which the backend tests run
        # without. Staticfiles dirs come before app dirs, so they win over
        # a local build too. The CSS references another file, as the real
        # font and icon styles do, so the storage rewrites it.
        source = tempfile.mkdtemp(prefix="content_studio_source_")
        self.addCleanup(shutil.rmtree, source)
        for name in ENTRY_FILES:
            path = Path(source, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("/* stand-in */\n" * 100)
        font = Path(source, "content_studio/fonts/inter/inter.woff2")
        font.write_bytes(b"font")
        Path(source, "content_studio/fonts/inter/index.css").write_text(
            '@font-face { src: url("inter.woff2") format("woff2"); }\n'
        )
        self.source = source

        self.static_root = tempfile.mkdtemp(prefix="content_studio_static_")
        self.addCleanup(shutil.rmtree, self.static_root)

    def collect_and_render(self, backend):
        settings = override_settings(
            DEBUG=False,
            STATIC_URL="/static/",
            STATIC_ROOT=self.static_root,
            STATICFILES_DIRS=[self.source],
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {"BACKEND": backend},
            },
        )
        settings.enable()
        self.addCleanup(settings.disable)

        call_command("collectstatic", interactive=False, verbosity=0)
        return self.client.get("/")

    def assert_renders(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'window.DCS_STATIC_PREFIX = "/static/content_studio/";'
        )

        # Every file the page references was collected under its hashed
        # name, and the stylesheet points at the hashed font.
        names = re.findall(
            r'(?:src|href)="?/static/([^"?\s>]+)', response.content.decode()
        )
        self.assertEqual(len(names), len(ENTRY_FILES))
        for name in names:
            self.assertNotIn(name, ENTRY_FILES)
            self.assertTrue(Path(self.static_root, name).is_file(), name)
        styles = [n for n in names if n.startswith("content_studio/fonts/")]
        css = Path(self.static_root, styles[0]).read_text()
        self.assertRegex(css, r'url\("inter\.[0-9a-f]{12}\.woff2"\)')

    def test_manifest_storage(self):
        response = self.collect_and_render(
            f"{__name__}.StrictManifestStaticFilesStorage"
        )

        self.assert_renders(response)

    def test_whitenoise_compressed_manifest_storage(self):
        try:
            import whitenoise  # noqa: F401
        except ImportError:
            self.skipTest("WhiteNoise is not installed")

        response = self.collect_and_render(
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )

        self.assert_renders(response)
        # WhiteNoise also wrote the compressed copies it serves (only for
        # files compression makes smaller, hence the long stand-ins).
        index_js = next(Path(self.static_root).glob("content_studio/assets/index.*.js"))
        self.assertTrue(index_js.with_name(index_js.name + ".gz").is_file())
