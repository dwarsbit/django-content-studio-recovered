"""
Answers /healthz and /readyz before Django looks at the Host header.

A platform's healthcheck calls the container on its internal IP, which
is not in ALLOWED_HOSTS; SecurityMiddleware and CommonMiddleware would
answer it with a 400. Put this middleware before them:

    MIDDLEWARE = [
        "content_studio.health.middleware.HealthCheckMiddleware",
        "django.middleware.security.SecurityMiddleware",
        ...
    ]

/statusz is left to the URLconf, so it keeps the Host check.
"""

from . import views

# The paths of content_studio.health.PROBE_PATHS.
PROBES = {"/healthz": views.healthz, "/readyz": views.readyz}


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        view = PROBES.get(request.path_info)

        if view is not None:
            return view(request)
        return self.get_response(request)
