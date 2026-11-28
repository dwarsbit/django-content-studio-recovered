"""
Tests for content_studio.contrib.settings: configure(), its sections and
merging, the Env reader and URL parsers, the SQL task queue, the tables
made after migrate and the deploy checks (E065, W040-W042).
"""

from pathlib import Path

from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection
from django.test import override_settings

from content_studio.contrib.settings import Env, configure
from content_studio.contrib.settings import checks as settings_checks
from content_studio.contrib.settings import sections
from content_studio.contrib.settings.env import (
    mail_settings,
    parse_cache_url,
    parse_database_url,
    parse_email_url,
)
from content_studio.contrib.settings.huey import SqlHuey

STRONG_KEY = "k3Y-9vQ!r2#Lm7@pX4$wZ8^tN1&bH6*sD0(fJ5)gU" + "a" * 10
BASE_ENV = {"DJANGO_SECRET_KEY": STRONG_KEY}


def run(env, namespace=None, **kwargs):
    return configure(
        namespace if namespace is not None else {},
        base_dir=Path("/srv/app"),
        env={**BASE_ENV, **env},
        **kwargs,
    )


# configure()


def test_requires_a_secret_key():
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        configure({}, base_dir=Path("/srv"), env={})


def test_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", STRONG_KEY)
    monkeypatch.setenv("PROJECT_NAME", "from-environ")
    assert configure({}, base_dir="/srv")["PROJECT_NAME"] == "from-environ"


def test_defaults_without_variables():
    s = run({})
    assert s["DEBUG"] is False
    assert s["PROJECT_NAME"] == "content-studio"
    assert s["SITE_URL"] == "http://localhost:8000"
    assert s["BACKEND_URL"] == "http://localhost:8000"
    assert s["MEDIA_URL"] == "http://localhost:8000/media/"
    assert s["MEDIA_ROOT"] == Path("/srv/app/media")
    assert s["STATIC_ROOT"] == Path("/srv/app/staticfiles")
    assert s["CSRF_TRUSTED_ORIGINS"] == ["http://localhost:8000"]
    assert s["DATABASES"]["default"] == {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/srv/app/db.sqlite3",
    }
    assert s["CACHES"]["default"]["BACKEND"].endswith("LocMemCache")
    assert s["CACHES"]["default"]["LOCATION"] == "content-studio"
    assert s["DEFAULT_FROM_EMAIL"] == "content-studio <noreply@localhost>"
    assert s["SERVER_EMAIL"] == s["DEFAULT_FROM_EMAIL"]
    assert s["CONTENT_STUDIO"]["ADMIN_URL"] == "http://localhost:8000/admin/"
    assert s["CONTENT_STUDIO"]["MEDIA_LIBRARY_MAX_UPLOAD_SIZE"] == 50 * 1024 * 1024
    assert s["CONTENT_STUDIO"]["NOTIFICATION_EMAIL_DIGEST"] is True
    assert s["CONTENT_STUDIO"]["IMAGE_SIZES"] == sections.DEFAULT_IMAGE_SIZES
    # Content Studio's own list of allowed extensions applies.
    assert "MEDIA_LIBRARY_ALLOWED_EXTENSIONS" not in s["CONTENT_STUDIO"]


def test_development_settings():
    s = run(
        {
            "DJANGO_DEBUG": "1",
            "SITE_URL": "http://localhost:3000",
            "BACKEND_URL": "http://localhost:8000/",
        }
    )
    assert s["DEBUG"] is True
    assert s["BACKEND_URL"] == "http://localhost:8000"
    assert {"localhost", "backend", "127.0.0.1"} <= set(s["ALLOWED_HOSTS"])
    assert s["CSRF_TRUSTED_ORIGINS"] == [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    assert s["MEDIA_URL"] == "http://localhost:8000/media/"
    assert s["SESSION_COOKIE_SECURE"] is False
    assert "SECURE_HSTS_SECONDS" not in s
    assert s["TASKS"]["default"]["BACKEND"].endswith("ImmediateBackend")
    assert s["STORAGES"]["staticfiles"]["BACKEND"] == (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


def test_production_settings():
    s = run(
        {
            "SITE_URL": "https://example.com",
            "BACKEND_URL": "https://api.example.com",
            "ALLOWED_HOSTS": "internal.example.com, ",
            "DATABASE_URL": "postgres://app:pw@db/app",
            "CACHE_URL": "redis://cache:6379/0",
            "NUM_PROXIES": "1",
            "PROJECT_NAME": "site",
        }
    )
    assert s["DEBUG"] is False
    assert s["ALLOWED_HOSTS"] == [
        "example.com",
        "api.example.com",
        "backend",
        "localhost",
        "127.0.0.1",
        "internal.example.com",
    ]
    assert s["SESSION_COOKIE_SECURE"] is True
    assert s["CSRF_COOKIE_SECURE"] is True
    assert s["SECURE_HSTS_SECONDS"] == 31536000
    assert s["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is False
    assert s["SECURE_HSTS_PRELOAD"] is False
    assert s["SECURE_SSL_REDIRECT"] is False
    assert s["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")
    assert s["MEDIA_URL"] == "https://api.example.com/media/"
    assert s["CACHES"]["default"]["KEY_PREFIX"] == "site"
    assert s["HUEY"]["connection"] == {"url": "redis://cache:6379/0"}
    assert s["HUEY"]["consumer"] == {"workers": 2, "worker_type": "thread"}
    assert s["TASKS"]["default"]["BACKEND"] == (
        "huey.contrib.djhuey.tasks_backend.HueyBackend"
    )
    assert s["REST_FRAMEWORK"]["NUM_PROXIES"] == 1
    assert s["HUEY_STATS"] == {"database": "psycopg3://app:pw@db/app"}
    assert s["DEFAULT_FROM_EMAIL"] == "site <noreply@example.com>"
    assert s["STORAGES"]["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )


def test_security_headers_are_always_on():
    s = run({})
    assert s["SESSION_COOKIE_HTTPONLY"] is True
    assert s["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert s["SECURE_CONTENT_TYPE_NOSNIFF"] is True
    assert s["SECURE_REFERRER_POLICY"] == "strict-origin-when-cross-origin"
    assert s["X_FRAME_OPTIONS"] == "DENY"
    assert s["REST_FRAMEWORK"]["NUM_PROXIES"] is None
    assert "SECURE_PROXY_SSL_HEADER" not in s


def test_hsts_opt_ins():
    s = run(
        {
            "SITE_URL": "https://example.com",
            "SECURE_HSTS_SECONDS": "60",
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": "yes",
            "SECURE_HSTS_PRELOAD": "on",
            "SECURE_SSL_REDIRECT": "true",
        }
    )
    assert s["SECURE_HSTS_SECONDS"] == 60
    assert s["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is True
    assert s["SECURE_HSTS_PRELOAD"] is True
    assert s["SECURE_SSL_REDIRECT"] is True


def test_deploy_checks_that_do_not_apply_are_silenced():
    s = run({"SITE_URL": "https://example.com", "NUM_PROXIES": "1"})
    assert {"security.W005", "security.W008", "security.W021"} <= set(
        s["SILENCED_SYSTEM_CHECKS"]
    )
    s = run({"SITE_URL": "https://example.com"})
    assert "security.W008" not in s["SILENCED_SYSTEM_CHECKS"]
    s = run(
        {
            "SITE_URL": "https://example.com",
            "NUM_PROXIES": "1",
            "SECURE_SSL_REDIRECT": "1",
        }
    )
    assert "security.W008" not in s["SILENCED_SYSTEM_CHECKS"]
    # W040 reports a weak key in place of Django's W009.
    assert run({"SITE_URL": "http://localhost:3000"})["SILENCED_SYSTEM_CHECKS"] == [
        "security.W009"
    ]


def test_silenced_checks_assigned_before_the_call_are_kept():
    s = run({}, {"SILENCED_SYSTEM_CHECKS": ["content_studio.W001"]})
    assert s["SILENCED_SYSTEM_CHECKS"] == ["content_studio.W001", "security.W009"]


# Merging


def test_dictionaries_are_merged_over_the_defaults():
    s = run(
        {},
        {
            "CONTENT_STUDIO": {"ADMIN_SITE": "config.studio.admin_site"},
            "REST_FRAMEWORK": {"PAGE_SIZE": 50},
        },
    )
    assert s["CONTENT_STUDIO"]["ADMIN_SITE"] == "config.studio.admin_site"
    assert s["CONTENT_STUDIO"]["ADMIN_URL"] == "http://localhost:8000/admin/"
    assert s["REST_FRAMEWORK"] == {"PAGE_SIZE": 50, "NUM_PROXIES": None}


def test_dictionaries_are_merged_one_level_deep():
    sizes = {"square": {"width": 100, "height": 100}}
    s = run({}, {"CONTENT_STUDIO": {"IMAGE_SIZES": sizes}})
    assert s["CONTENT_STUDIO"]["IMAGE_SIZES"] == sizes


def test_settings_assigned_after_the_call_override_it():
    namespace = run({})
    namespace["DEBUG"] = True
    assert namespace["DEBUG"] is True


def test_project_sections_run_after_the_built_in_ones():
    seen = {}

    def analytics(ctx):
        seen["settings"] = dict(ctx.settings)
        seen["secure"] = ctx.secure
        return {
            "CONTENT_STUDIO": {"ANALYTICS": ctx.env.str("UMAMI_URL")},
            "HEADLESS": {"PAGE_SIZE": 20},
            "X_FRAME_OPTIONS": "SAMEORIGIN",
        }

    s = run(
        {"UMAMI_URL": "http://umami:3000", "SITE_URL": "https://example.com"},
        {"HEADLESS": {"PAGE_SIZE": 10}},
        sections=[analytics],
    )
    # Sections add keys to the dictionary settings and replace others.
    assert s["CONTENT_STUDIO"]["ANALYTICS"] == "http://umami:3000"
    assert s["CONTENT_STUDIO"]["ADMIN_URL"] == "https://example.com/admin/"
    assert s["X_FRAME_OPTIONS"] == "SAMEORIGIN"
    # The project's own dictionary still wins.
    assert s["HEADLESS"] == {"PAGE_SIZE": 10}
    assert seen["secure"] is True
    assert seen["settings"]["SITE_URL"] == "https://example.com"


def test_sections_read_the_namespace_as_it_was():
    def peek(ctx):
        assert ctx.namespace["BASE_DIR"] == "/srv"
        with pytest.raises(TypeError):
            ctx.namespace["DEBUG"] = True  # type: ignore[index]
        return {}

    run({}, {"BASE_DIR": "/srv"}, sections=[peek])


# Database


def test_database_urls():
    s = run({"DATABASE_URL": "postgres://app:p%40ss@db:5432/site?sslmode=require"})
    database = s["DATABASES"]["default"]
    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["PASSWORD"] == "p@ss"
    assert database["OPTIONS"] == {"sslmode": "require"}
    # Under ASGI a kept connection is never reused and they pile up.
    assert database["CONN_MAX_AGE"] == 0


def test_database_pool(monkeypatch):
    monkeypatch.setattr(sections, "_installed", lambda module: True)
    database = run(
        {
            "DATABASE_URL": "postgres://app:pw@db/app?sslmode=require",
            "DATABASE_POOL": "1",
        }
    )["DATABASES"]["default"]
    assert database["CONN_MAX_AGE"] == 0
    assert database["OPTIONS"] == {
        "sslmode": "require",
        "pool": {"min_size": 1, "max_size": 4},
    }
    sized = run(
        {
            "DATABASE_URL": "postgres://app:pw@db/app",
            "DATABASE_POOL": "1",
            "DATABASE_POOL_SIZE": "8",
        }
    )
    assert sized["DATABASES"]["default"]["OPTIONS"]["pool"]["max_size"] == 8
    no_pool = run({"DATABASE_URL": "postgres://app:pw@db/app"})
    assert "OPTIONS" not in no_pool["DATABASES"]["default"]
    # SQLite has no pool; the setting is ignored.
    assert "OPTIONS" not in run({"DATABASE_POOL": "1"})["DATABASES"]["default"]


def test_database_pool_needs_psycopg_pool(monkeypatch):
    monkeypatch.setattr(sections, "_installed", lambda module: False)
    with pytest.raises(ImproperlyConfigured, match=r"psycopg_pool.*\[server\]"):
        run({"DATABASE_URL": "postgres://app:pw@db/app", "DATABASE_POOL": "1"})
    monkeypatch.setattr(sections, "_installed", lambda module: True)
    with pytest.raises(ImproperlyConfigured, match="DATABASE_POOL_SIZE"):
        run(
            {
                "DATABASE_URL": "postgres://app:pw@db/app",
                "DATABASE_POOL": "1",
                "DATABASE_POOL_SIZE": "0",
            }
        )


# Tasks

POSTGRES = {
    "DATABASE_URL": "postgres://app:pw@db/app?sslmode=require",
    "PROJECT_NAME": "site",
}


def test_tasks_in_the_database():
    s = run({**POSTGRES, "CACHE_URL": "db://", "TASKS_URL": "db://"})
    assert s["CACHES"]["default"]["BACKEND"].endswith("DatabaseCache")
    assert s["HUEY"]["huey_class"] == "content_studio.contrib.settings.huey.SqlHuey"
    assert s["HUEY"]["database"] == "psycopg3://app:pw@db/app?sslmode=require"
    assert s["HUEY"]["create_tables"] is False
    assert s["HUEY"]["immediate"] is False
    assert s["HUEY"]["name"] == "site"
    assert s["TASKS"]["default"]["BACKEND"] == (
        "huey.contrib.djhuey.tasks_backend.HueyBackend"
    )


@pytest.mark.parametrize("scheme", ["postgresql", "pgsql", "postgis"])
def test_tasks_in_the_database_with_every_postgres_scheme(scheme):
    s = run({"DATABASE_URL": f"{scheme}://app:pw@db/app", "TASKS_URL": "db://"})
    assert s["HUEY"]["database"] == "psycopg3://app:pw@db/app"
    assert s["HUEY_STATS"] == {"database": "psycopg3://app:pw@db/app"}


def test_tasks_in_a_sqlite_database():
    s = run({"DATABASE_URL": "sqlite:////srv/app/db.sqlite3", "TASKS_URL": "db://"})
    assert s["HUEY"]["database"] == "sqlite:////srv/app/db.sqlite3"
    assert "HUEY_STATS" not in s


def test_huey_stats_set_by_the_project_are_kept():
    s = run(POSTGRES, {"HUEY_STATS": {"database": "sqlite:///stats.db"}})
    assert s["HUEY_STATS"] == {"database": "sqlite:///stats.db"}


def test_tasks_on_valkey_with_the_database_cache():
    s = run(
        {
            **POSTGRES,
            "CACHE_URL": "db://",
            "TASKS_URL": "valkey://cache:6379/1",
            "HUEY_WORKERS": "4",
        }
    )
    assert s["HUEY"]["huey_class"] == "huey.RedisHuey"
    assert s["HUEY"]["connection"] == {"url": "redis://cache:6379/1"}
    assert s["HUEY"]["consumer"]["workers"] == 4


def test_tasks_in_the_request():
    s = run(
        {**POSTGRES, "CACHE_URL": "redis://cache:6379/0", "TASKS_URL": "immediate://"}
    )
    assert s["HUEY"]["immediate"] is True
    assert s["TASKS"]["default"]["BACKEND"].endswith("ImmediateBackend")


def test_tasks_without_tasks_url_follow_a_redis_cache():
    assert run({**POSTGRES, "CACHE_URL": "db://"})["HUEY"]["immediate"] is True
    redis = run({**POSTGRES, "CACHE_URL": "redis://cache:6379/0"})
    assert redis["HUEY"]["huey_class"] == "huey.RedisHuey"


def test_tasks_run_immediately_without_huey(monkeypatch):
    monkeypatch.setattr(sections, "_installed", lambda module: module != "huey")
    s = run({**POSTGRES, "TASKS_URL": "db://"})
    assert s["HUEY"]["immediate"] is True
    assert s["TASKS"]["default"]["BACKEND"].endswith("ImmediateBackend")


def test_unknown_tasks_url():
    with pytest.raises(ImproperlyConfigured, match="TASKS_URL"):
        run({**POSTGRES, "TASKS_URL": "amqp://queue"})


def test_database_tasks_need_postgres_or_sqlite():
    with pytest.raises(ImproperlyConfigured, match="TASKS_URL=db://"):
        sections.task_settings("db://", None, "mysql://db/app", "site", Env({}))


# Storage


def test_s3_storage():
    s = run(
        {
            "S3_BUCKET": "media",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_REGION": "eu-west-1",
            "S3_ENDPOINT_URL": "https://s3.example.com",
            "S3_CUSTOM_DOMAIN": "cdn.example.com",
        }
    )
    storage = s["STORAGES"]["default"]
    assert storage["BACKEND"] == "storages.backends.s3.S3Storage"
    assert storage["OPTIONS"] == {
        "bucket_name": "media",
        "access_key": "key",
        "secret_key": "secret",
        "region_name": "eu-west-1",
        "endpoint_url": "https://s3.example.com",
        "querystring_auth": False,
        "file_overwrite": False,
        "custom_domain": "cdn.example.com",
    }
    assert s["MEDIA_URL"] == "https://cdn.example.com/"


def test_s3_public_url():
    s = run(
        {
            "S3_BUCKET": "media",
            "S3_ENDPOINT_URL": "http://s3:8333",
            "S3_PUBLIC_URL": "http://localhost:8333/media/",
            "S3_QUERYSTRING_AUTH": "1",
        }
    )
    options = s["STORAGES"]["default"]["OPTIONS"]
    assert options["custom_domain"] == "localhost:8333/media"
    assert options["url_protocol"] == "http:"
    assert options["querystring_auth"] is True
    assert s["MEDIA_URL"] == "http://localhost:8333/media/"


def test_s3_without_a_public_url_keeps_media_url():
    s = run({"S3_BUCKET": "media", "MEDIA_URL": "https://files.example.com/"})
    assert s["MEDIA_URL"] == "https://files.example.com/"
    assert "custom_domain" not in s["STORAGES"]["default"]["OPTIONS"]


def test_media_root():
    assert run({"MEDIA_ROOT": "/data/media"})["MEDIA_ROOT"] == Path("/data/media")


def test_image_sizes_need_pillow(monkeypatch):
    monkeypatch.setattr(sections, "_installed", lambda module: module != "PIL")
    assert "IMAGE_SIZES" not in run({})["CONTENT_STUDIO"]


def test_upload_size():
    s = run({"MEDIA_MAX_UPLOAD_SIZE": "1024"})
    assert s["CONTENT_STUDIO"]["MEDIA_LIBRARY_MAX_UPLOAD_SIZE"] == 1024


# Mail


def test_mail_settings():
    s = run(
        {
            "EMAIL_URL": "smtp+tls://user:p%40ss@mail.example.com",
            "DEFAULT_FROM_EMAIL": "Site <hello@example.com>",
        }
    )
    assert s["DEFAULT_FROM_EMAIL"] == "Site <hello@example.com>"
    assert s["SERVER_EMAIL"] == "Site <hello@example.com>"
    mailer = mail_settings(parse_email_url("smtp+tls://user:p%40ss@mail.example.com"))
    for name, value in mailer.items():
        assert s[name] == value


def test_mail_settings_by_django_version(monkeypatch):
    import django

    mailer = parse_email_url("smtp+tls://user:secret@mail.example.com")
    monkeypatch.setattr(django, "VERSION", (6, 1, 0, "final", 0))
    assert mail_settings(mailer) == {"MAILERS": {"default": mailer}}
    monkeypatch.setattr(django, "VERSION", (5, 2, 0, "final", 0))
    assert mail_settings(mailer) == {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": "mail.example.com",
        "EMAIL_PORT": 587,
        "EMAIL_HOST_USER": "user",
        "EMAIL_HOST_PASSWORD": "secret",
        "EMAIL_USE_TLS": True,
        "EMAIL_USE_SSL": False,
    }


# Env and URL parsers


def test_env_values():
    env = Env({"FLAG": "yes", "COUNT": "3", "HOSTS": "a.com, b.com,", "EMPTY": ""})
    assert env.bool("FLAG") is True
    assert env.bool("EMPTY", default=True) is False
    assert env.bool("MISSING", default=True) is True
    assert env.int("COUNT") == 3
    assert env.int("EMPTY", 7) == 7
    assert env.list("HOSTS") == ["a.com", "b.com"]
    assert env.list("MISSING") == []
    assert env.str("EMPTY", "fallback") == "fallback"
    with pytest.raises(ImproperlyConfigured, match="Set the MISSING environment"):
        env.str("MISSING", required=True)
    with pytest.raises(ImproperlyConfigured):
        Env({"FLAG": "maybe"}).bool("FLAG")
    with pytest.raises(ImproperlyConfigured):
        Env({"COUNT": "three"}).int("COUNT")


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_env_true_values(value):
    assert Env({"FLAG": value}).bool("FLAG") is True


@pytest.mark.parametrize("value", ["0", "false", "No", "off", ""])
def test_env_false_values(value):
    assert Env({"FLAG": value}).bool("FLAG", default=True) is False


def test_postgres_url():
    config = parse_database_url("postgres://app:p%40ss@db:5432/site?sslmode=require")
    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "site"
    assert config["USER"] == "app"
    assert config["PASSWORD"] == "p@ss"
    assert config["HOST"] == "db"
    assert config["PORT"] == "5432"
    assert config["OPTIONS"] == {"sslmode": "require"}
    assert config["CONN_MAX_AGE"] == 0
    assert parse_database_url("postgis://db/site")["ENGINE"] == (
        "django.contrib.gis.db.backends.postgis"
    )


def test_sqlite_url():
    assert parse_database_url("sqlite:////srv/db.sqlite3")["NAME"] == "/srv/db.sqlite3"
    assert parse_database_url("sqlite://:memory:")["NAME"] == ":memory:"


def test_unsupported_database_url():
    with pytest.raises(ImproperlyConfigured):
        parse_database_url("mysql://localhost/db")


def test_cache_urls():
    assert parse_cache_url("redis://cache:6379/0")["BACKEND"].endswith("RedisCache")
    assert parse_cache_url("valkey://cache:6379/0")["LOCATION"] == (
        "redis://cache:6379/0"
    )
    assert parse_cache_url("valkeys://cache:6379/0")["LOCATION"] == (
        "rediss://cache:6379/0"
    )
    assert parse_cache_url("locmem://")["BACKEND"].endswith("LocMemCache")
    assert parse_cache_url("dummy://")["BACKEND"].endswith("DummyCache")
    database = parse_cache_url("db://", key_prefix="site")
    assert database["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    assert database["LOCATION"] == "django_cache"
    assert database["KEY_PREFIX"] == "site"
    with pytest.raises(ImproperlyConfigured):
        parse_cache_url("memcached://cache")


def test_email_urls():
    smtp = parse_email_url("smtp://user:secret@mail.example.com:2525")["OPTIONS"]
    assert smtp["host"] == "mail.example.com"
    assert smtp["port"] == 2525
    assert smtp["password"] == "secret"
    assert smtp["use_tls"] is False
    tls = parse_email_url("smtp+tls://mail.example.com")["OPTIONS"]
    assert (tls["port"], tls["use_tls"]) == (587, True)
    assert parse_email_url("smtps://mail.example.com")["OPTIONS"]["use_ssl"] is True
    assert parse_email_url("console://")["BACKEND"].endswith("console.EmailBackend")
    with pytest.raises(ImproperlyConfigured):
        parse_email_url("sendgrid://key")


# The SQL task queue and the tables made after migrate


def test_sql_queue_prefixes_its_tables(tmp_path):
    huey = SqlHuey(
        "site", database=f"sqlite:///{tmp_path / 'queue.db'}", create_tables=False
    )
    huey.storage.create_tables()
    tables = {model._meta.table_name for model in (huey.storage.Task, huey.storage.KV)}
    assert tables == {"huey_task", "huey_kv"}

    @huey.task()
    def add(a, b):
        return a + b

    result = add(1, 2)
    assert huey.pending_count() == 1
    huey.execute(huey.dequeue())
    assert result.get() == 3


@pytest.mark.django_db
def test_migrate_creates_the_cache_table(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        }
    }
    call_command("migrate", verbosity=0)
    assert "django_cache" in connection.introspection.table_names()


@pytest.mark.django_db
def test_migrate_creates_the_queue_tables(settings, tmp_path, monkeypatch):
    from huey.contrib import djhuey

    huey = SqlHuey(
        "site", database=f"sqlite:///{tmp_path / 'queue.db'}", create_tables=False
    )
    settings.HUEY = {"huey_class": sections.SQL_HUEY}
    monkeypatch.setattr(djhuey, "HUEY", huey)
    call_command("migrate", verbosity=0)
    assert set(huey.storage.database.get_tables()) >= {"huey_task", "huey_kv"}


@pytest.mark.parametrize(
    "using,huey_class",
    [("other", sections.SQL_HUEY), ("default", "huey.RedisHuey")],
)
def test_queue_tables_only_for_the_sql_queue_on_default(
    settings, tmp_path, monkeypatch, using, huey_class
):
    from huey.contrib import djhuey

    from content_studio.contrib.settings import apps as settings_apps

    huey = SqlHuey(
        "site", database=f"sqlite:///{tmp_path / 'queue.db'}", create_tables=False
    )
    settings.HUEY = {"huey_class": huey_class}
    monkeypatch.setattr(djhuey, "HUEY", huey)

    with mock.patch("django.core.management.call_command") as command:
        settings_apps.create_tables(sender=None, using=using)

    command.assert_called_once_with("createcachetable", database=using, verbosity=0)
    assert huey.storage.database.get_tables() == []


# Deploy checks


@override_settings(DEBUG=True)
def test_debug_is_an_error_in_a_deploy_check():
    [error] = settings_checks.check_debug()
    assert error.id == "content_studio.E065"


@override_settings(DEBUG=False)
def test_debug_off():
    assert settings_checks.check_debug() == []


@pytest.mark.parametrize(
    "key,reason",
    [
        ("django-insecure-" + "x1y2z3" * 10, "placeholder"),
        ("change-me-to-a-long-random-value-before-you-deploy-this", "placeholder"),
        ("a1b2c3", "short"),
        ("ab" * 40, "short"),
        (STRONG_KEY, None),
    ],
)
def test_weak_secret_keys(key, reason):
    assert settings_checks.is_weak_secret_key(key) == reason


def test_secret_key_warning():
    with override_settings(SECRET_KEY="changeme" * 10):
        [warning] = settings_checks.check_secret_key()
    assert warning.id == "content_studio.W040"
    assert "placeholder" in warning.msg
    assert "get_random_secret_key" in warning.hint
    with override_settings(SECRET_KEY="short-but-random-q8Z"):
        [warning] = settings_checks.check_secret_key()
    assert "shorter than 50" in warning.msg
    with override_settings(SECRET_KEY=STRONG_KEY):
        assert settings_checks.check_secret_key() == []


def test_unshared_cache_warning():
    locmem = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    with override_settings(CACHES=locmem):
        [warning] = settings_checks.check_cache()
    assert warning.id == "content_studio.W041"
    database = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        }
    }
    with override_settings(CACHES=database):
        assert settings_checks.check_cache() == []


def test_proxy_warning():
    with override_settings(
        SITE_URL="https://example.com", SECURE_PROXY_SSL_HEADER=None
    ):
        [warning] = settings_checks.check_proxy()
    assert warning.id == "content_studio.W042"
    assert "NUM_PROXIES" in warning.hint
    with override_settings(
        SITE_URL="https://example.com",
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    ):
        assert settings_checks.check_proxy() == []
    with override_settings(SITE_URL="http://localhost:8000"):
        assert settings_checks.check_proxy() == []


def test_checks_run_only_in_a_deploy_check():
    from django.core.checks import registry

    def ours(deploy):
        return {
            check.__name__
            for check in registry.registry.get_checks(deploy)
            if check.__module__ == settings_checks.__name__
        }

    assert ours(True) == {
        "check_debug",
        "check_secret_key",
        "check_cache",
        "check_proxy",
    }
    assert ours(False) == set()


# Logging


def test_logging_follows_debug():
    production = run({})["LOGGING"]
    assert production["handlers"]["console"]["formatter"] == "json"
    assert production["root"]["level"] == "INFO"
    assert production["loggers"]["content_studio.access"]["level"] == "INFO"

    development = run({"DJANGO_DEBUG": "1"})["LOGGING"]
    assert development["handlers"]["console"]["formatter"] == "plain"
    assert development["loggers"]["content_studio.access"]["level"] == "WARNING"


def test_logging_variables():
    config = run({"LOG_FORMAT": "plain", "LOG_LEVEL": "warning", "LOG_ACCESS": "0"})[
        "LOGGING"
    ]
    assert config["handlers"]["console"]["formatter"] == "plain"
    assert config["root"]["level"] == "WARNING"
    assert config["loggers"]["content_studio.access"]["level"] == "WARNING"

    config = run({"DJANGO_DEBUG": "1", "LOG_FORMAT": "JSON", "LOG_ACCESS": "1"})[
        "LOGGING"
    ]
    assert config["handlers"]["console"]["formatter"] == "json"
    assert config["loggers"]["content_studio.access"]["level"] == "INFO"


@pytest.mark.parametrize(
    "env, message",
    [
        ({"LOG_FORMAT": "xml"}, "LOG_FORMAT must be"),
        ({"LOG_LEVEL": "LOUD"}, "LOG_LEVEL must be"),
    ],
)
def test_logging_refuses_unknown_values(env, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        run(env)
