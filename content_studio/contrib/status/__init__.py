"""
The system status page: the services a site depends on with how they
are doing, the tasks waiting, running and finished, and the recurring
tasks.

Add "content_studio.contrib.status" to INSTALLED_APPS. Other apps add
their own services and tasks from their AppConfig.ready():

    from content_studio.contrib import status

    def check_search():
        if not search.ping():
            return status.down("Elasticsearch", message="No answer on port 9200.")
        return status.ok("Elasticsearch 8.15")

    status.register_service("shop.search", "Search", check_search)

Registering works whether or not the status app is installed; without
it nothing is shown.
"""

from .registry import (
    Run,
    ServiceResult,
    ServiceStatus,
    degraded,
    down,
    ok,
    register_recurring_task,
    register_service,
    register_task,
    register_task_adapter,
    unknown,
)

__all__ = [
    "Run",
    "ServiceResult",
    "ServiceStatus",
    "degraded",
    "down",
    "ok",
    "register_recurring_task",
    "register_service",
    "register_task",
    "register_task_adapter",
    "unknown",
]
