"""
Django settings for testing content_studio.
"""

import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-test-key-for-content-studio-tests-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "content_studio",
    "content_studio.contrib.password_reset",
    "content_studio.contrib.two_factor",
    "content_studio.contrib.status",
    "content_studio.contrib.backups",
    "content_studio.contrib.email_activity",
    "content_studio.contrib.captcha",
    "content_studio.contrib.settings",
    "content_studio.media_library",
    "content_studio.webhooks",
    "content_studio.notifications",
    "content_studio.history",
    "content_studio.preferences",
    "content_studio.previews",
    "content_studio.comments",
    "content_studio.review",
    "tests.testapp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "content_studio.previews.middleware.PreviewMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "tests.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Run the tests on PostgreSQL: TEST_POSTGRES_HOST=localhost pytest
if os.environ.get("TEST_POSTGRES_HOST"):
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ["TEST_POSTGRES_HOST"],
        "PORT": os.environ.get("TEST_POSTGRES_PORT", "5432"),
        "NAME": os.environ.get("TEST_POSTGRES_DB", "content_studio"),
        "USER": os.environ.get("TEST_POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("TEST_POSTGRES_PASSWORD", "postgres"),
        # The test app has no migrations and refers to auth's tables,
        # which PostgreSQL checks at once: make every table in one go.
        "TEST": {"MIGRATE": False},
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Keep test uploads out of the repository: file fields write to a
# throwaway directory instead of the default media/ next to the CWD.
MEDIA_ROOT = tempfile.mkdtemp(prefix="content_studio_tests_")

# Keep test emails out of SMTP
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    # Backups (content_studio.contrib.backups) stay in memory.
    "backups": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
}

# Content Studio settings
CONTENT_STUDIO = {
    "ADMIN_SITE": "content_studio.admin.admin_site",
    "BACKUP_STORAGE": "backups",
    # Scheduled backups are off; the tests set a schedule where needed.
    "BACKUP_SCHEDULE": None,
    # Translated content (test_translations): English first, the default.
    "CONTENT_LANGUAGES": [("en", "English"), ("nl", "Dutch"), ("de", "German")],
}
