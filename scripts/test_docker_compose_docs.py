"""
Runs the files of the Docker Compose docs page in a fresh project.

Creates a project in a new directory, copies every code block with a
title="<path>" from website/docs/docker-compose.mdx into it as it is, and
runs it with Docker Compose: first in development, then in production
behind Caddy at https://site.localhost. Needs Docker with Compose, uv and
curl, and ports 80, 443, 8000 and 8025 free.

    python scripts/test_docker_compose_docs.py [project directory]
"""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "website" / "docs" / "docker-compose.mdx"
FILE_BLOCK = re.compile(r'^```\w+ title="([^"]+)"\n(.*?)^```$', re.S | re.M)
SITE = "https://site.localhost"
PASSWORD = "Compose-test-1234"

PYPROJECT = """\
[project]
name = "mysite"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "django-content-studio[server,huey]",
    "gunicorn",
    "uvicorn-worker",
]
"""

SETTINGS = """\
from pathlib import Path

from content_studio.contrib.settings import configure

BASE_DIR = Path(__file__).resolve().parent.parent

CONTENT_STUDIO = {
    "ADMIN_SITE": "config.studio.admin_site",
}

configure(globals(), base_dir=BASE_DIR)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "huey.contrib.djhuey",
    "content_studio",
    "content_studio.media_library",
    "content_studio.contrib.settings",
]

{middleware}

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
"""

URLS = """\
from django.urls import include, path

urlpatterns = [
    path("", include("content_studio.health.urls")),
    path("admin/", include("content_studio.urls")),
]
"""

STUDIO = """\
from content_studio.admin import ContentStudioSite

admin_site = ContentStudioSite()
"""


def run(*args: str, cwd: Path, input: str | None = None) -> str:
    print("$", " ".join(args), flush=True)
    result = subprocess.run(
        args, cwd=cwd, input=input, capture_output=True, text=True, check=False
    )

    if result.returncode:
        print(result.stdout, result.stderr, sep="\n")
        raise SystemExit(f"Failed: {' '.join(args)}")

    return result.stdout


def curl(*args: str, cwd: Path) -> str:
    return run("curl", "--silent", "--noproxy", "*", *args, cwd=cwd)


def status(url: str, cwd: Path, *args: str) -> int:
    return int(
        curl(
            "--output", "/dev/null", "--write-out", "%{http_code}", *args, url, cwd=cwd
        )
    )


def expect(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise SystemExit(f"{label}: expected {expected!r}, got {actual!r}")

    print(f"ok  {label}: {actual!r}", flush=True)


def set_env(project: Path, **values: str) -> None:
    env = project / ".env"
    text = env.read_text()

    for name, value in values.items():
        line = f"{name}={value}"
        pattern = re.compile(rf"^#? ?{name}=.*$", re.M)
        text = (
            pattern.sub(line, text, count=1)
            if pattern.search(text)
            else f"{text}{line}\n"
        )

    env.write_text(text)


def create_project(project: Path) -> None:
    page = PAGE.read_text()
    middleware = re.search(r"^MIDDLEWARE = \[\n.*?^\]$", page, re.S | re.M)
    assert middleware, "No MIDDLEWARE block on the page."

    (project / "config").mkdir(parents=True)
    (project / "pyproject.toml").write_text(PYPROJECT)
    (project / "config" / "__init__.py").write_text("")
    (project / "config" / "settings.py").write_text(
        SETTINGS.replace("{middleware}", middleware.group(0))
    )
    (project / "config" / "urls.py").write_text(URLS)
    (project / "config" / "studio.py").write_text(STUDIO)
    run("uv", "lock", cwd=project)
    run("uv", "sync", cwd=project)
    run("uv", "run", "django-admin", "startproject", "config", "tmp", cwd=project)
    tmp = project / "tmp"
    (tmp / "manage.py").rename(project / "manage.py")
    (tmp / "config" / "asgi.py").rename(project / "config" / "asgi.py")

    for match in FILE_BLOCK.finditer(page):
        path = project / match.group(1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(match.group(2))
        print("copied", match.group(1))

    set_env(
        project,
        DJANGO_SECRET_KEY=secrets.token_urlsafe(50),
        POSTGRES_PASSWORD=secrets.token_hex(16),
    )


def compose(project: Path, *args: str) -> str:
    return run("docker", "compose", *args, cwd=project)


def up(project: Path) -> None:
    try:
        compose(project, "up", "--detach", "--build", "--wait", "--wait-timeout", "300")
    except SystemExit:
        print(compose(project, "ps", "--all"), compose(project, "logs"), sep="\n")
        raise


def test_development(project: Path) -> None:
    up(project)
    expect("dev /readyz", status("http://127.0.0.1:8000/readyz", project), 200)
    expect("dev /admin/", status("http://127.0.0.1:8000/admin/", project), 200)
    compose(
        project,
        "exec",
        "-T",
        "worker",
        "python",
        "manage.py",
        "content_studio_worker_alive",
    )
    compose(
        project,
        "exec",
        "-T",
        "backend",
        "python",
        "manage.py",
        "sendtestemail",
        "a@example.com",
    )
    time.sleep(1)
    messages = json.loads(curl("http://127.0.0.1:8025/api/v1/messages", cwd=project))
    expect("dev mail in Mailpit", messages["total"], 1)
    compose(project, "down")


def test_production(project: Path) -> None:
    set_env(
        project,
        COMPOSE_PROFILES="prod,db",
        COMPOSE_FILE="compose.yaml:compose.ports.yaml",
        SITE_URL=SITE,
        DJANGO_DEBUG="0",
    )
    up(project)

    # Caddy signs .localhost names with its own local authority.
    root = project / "caddy-root.crt"
    compose(
        project, "cp", "proxy:/data/caddy/pki/authorities/local/root.crt", str(root)
    )
    tls = ("--cacert", str(root))

    expect("prod /admin/", status(f"{SITE}/admin/", project, *tls), 200)

    for path in ("/healthz", "/readyz", "/statusz"):
        expect(f"prod {path}", status(f"{SITE}{path}", project, *tls), 404)

    headers = curl(
        "--head",
        "--header",
        "X-Request-ID: from-client",
        *tls,
        f"{SITE}/admin/",
        cwd=project,
    ).lower()

    for header in (
        "strict-transport-security:",
        "x-content-type-options: nosniff",
        "referrer-policy:",
        "x-frame-options:",
    ):
        expect(f"prod header {header}", header in headers, True)

    expect("prod no Server header", "\nserver:" in headers, False)
    request_id = re.search(r"^x-request-id: (\S+)", headers, re.M)
    expect(
        "prod request ID replaced",
        bool(request_id) and request_id.group(1) != "from-client",
        True,
    )

    static = compose(
        project,
        "exec",
        "-T",
        "backend-prod",
        "sh",
        "-c",
        "ls staticfiles/admin/css/base.*.css",
    ).split()[0]
    expect(
        "prod static file",
        status(f"{SITE}/static/{static.removeprefix('staticfiles/')}", project, *tls),
        200,
    )

    upload = project / "upload.txt"
    upload.write_text("An upload.")
    compose(project, "cp", str(upload), "backend-prod:/app/media/upload.txt")
    media = curl("--head", *tls, f"{SITE}/media/upload.txt", cwd=project).lower()
    expect("prod media 200", media.startswith("http/2 200"), True)
    expect(
        "prod media CSP", "content-security-policy: script-src 'none'" in media, True
    )

    compose(
        project,
        "exec",
        "-T",
        "-e",
        f"DJANGO_SUPERUSER_PASSWORD={PASSWORD}",
        "backend-prod",
        "python",
        "manage.py",
        "createsuperuser",
        "--noinput",
        "--username",
        "admin",
        "--email",
        "admin@example.com",
    )
    login = status(
        f"{SITE}/admin/api/login/usernamepassword",
        project,
        *tls,
        "--header",
        "Content-Type: application/json",
        "--data",
        json.dumps({"username": "admin", "password": PASSWORD}),
    )
    expect("prod login", login, 200)

    for service in ("backend-prod", "worker-prod"):
        user = compose(project, "exec", "-T", service, "id", "-un").strip()
        expect(f"prod {service} user", user, "app")

    for service in ("backend-prod", "worker-prod", "proxy"):
        written = subprocess.run(
            ["docker", "compose", "exec", "-T", service, "touch", "/written"],
            cwd=project,
            capture_output=True,
            check=False,
        )
        expect(f"prod {service} read-only", written.returncode != 0, True)

    logs = compose(project, "logs", "--no-log-prefix", "proxy")
    expect("prod Caddy logs the request ID", request_id.group(1) in logs, True)
    compose(
        project,
        "exec",
        "-T",
        "worker-prod",
        "python",
        "manage.py",
        "content_studio_worker_alive",
    )
    compose(project, "down", "--volumes")


def main() -> None:
    project = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()) / "mysite"
    )
    create_project(project)
    test_development(project)
    test_production(project)
    print("The Docker Compose page works.")


if __name__ == "__main__":
    main()
