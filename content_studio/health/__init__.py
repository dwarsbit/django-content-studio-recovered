"""
Health checks for container orchestrators: /healthz, /readyz and
/statusz, a middleware that answers the first two before the Host check,
a worker heartbeat and the content_studio_worker_alive command.

    # urls.py
    urlpatterns = [
        path("", include("content_studio.health.urls")),
        path("admin/", include("content_studio.urls")),
    ]

    # settings.py
    MIDDLEWARE = [
        "content_studio.health.middleware.HealthCheckMiddleware",
        "django.middleware.security.SecurityMiddleware",
        ...
    ]

The heartbeat runs on Huey's consumer by itself. With another task
backend, call beat() every minute from a worker.
"""

from .checks import (
    ERROR,
    OFF,
    OK,
    CheckResult,
    check_cache,
    check_database,
    check_worker,
)
from .heartbeat import beat, get_last_beat

# The paths HealthCheckMiddleware answers, and every health endpoint's
# path, as request.path_info has them.
PROBE_PATHS = ("/healthz", "/readyz")
HEALTH_PATHS = ("/healthz", "/readyz", "/statusz")

__all__ = [
    "ERROR",
    "HEALTH_PATHS",
    "OFF",
    "OK",
    "PROBE_PATHS",
    "CheckResult",
    "beat",
    "check_cache",
    "check_database",
    "check_worker",
    "get_last_beat",
]
