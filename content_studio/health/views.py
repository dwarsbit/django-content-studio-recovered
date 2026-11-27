"""
The health endpoints, for a container orchestrator's healthchecks:

- /healthz: the process answers.
- /readyz: the database and the cache work.
- /statusz: the database, the cache and the worker.

Each check answers "ok", "error" or "off"; only "error" makes the answer
503. The endpoints need no login and show nothing but those words.
"""

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from . import checks

READY_CHECKS = ("database", "cache")
STATUS_CHECKS = ("database", "cache", "worker")


def run_checks(names) -> dict[str, str]:
    return {name: getattr(checks, f"check_{name}")().status for name in names}


def report(names) -> JsonResponse:
    results = run_checks(names)
    healthy = checks.ERROR not in results.values()

    return JsonResponse(
        {"status": checks.OK if healthy else checks.ERROR, "checks": results},
        status=200 if healthy else 503,
    )


@never_cache
@require_safe
def healthz(request):
    return JsonResponse({"status": checks.OK})


@never_cache
@require_safe
def readyz(request):
    return report(READY_CHECKS)


@never_cache
@require_safe
def statusz(request):
    return report(STATUS_CHECKS)
