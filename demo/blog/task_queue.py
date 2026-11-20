"""
A made-up task backend for the demo's task dashboard: an adapter that
reports fixed numbers and tasks, so the page shows without a queue.
A real project writes an adapter for its own backend instead.
"""

from datetime import timedelta

from django.utils import timezone

from content_studio.dashboard.tasks import (
    TaskAdapter,
    TaskHealth,
    TaskRow,
    TaskStatistic,
    TaskStatus,
)


class DemoTaskAdapter(TaskAdapter):
    statistics = ("queued", "running", "succeeded", "failed")

    def get_statistics(self, request):
        return {
            "queued": TaskStatistic(3),
            "running": TaskStatistic(1),
            "succeeded": TaskStatistic(1284, trend=4.2),
            "failed": TaskStatistic(2, trend=-50),
        }

    def get_health(self):
        return TaskHealth("ok", "Demo queue · 3 queued")

    def get_pending_tasks(self, request, limit):
        now = timezone.now()
        return [
            TaskRow(
                title="Rebuild the sitemap",
                source="Blog",
                status=TaskStatus.RUNNING,
                last_run_at=now - timedelta(seconds=20),
            ),
            TaskRow(
                title="Make image sizes: harbor-at-dusk.jpg",
                source="Media library",
                status=TaskStatus.QUEUED,
            ),
            TaskRow(
                title="Deliver webhook: article.published",
                source="Webhooks",
                status=TaskStatus.QUEUED,
            ),
            TaskRow(
                title="Purge CDN cache: /travel/",
                source="Blog",
                status=TaskStatus.QUEUED,
            ),
        ][:limit]

    def get_periodic_tasks(self, request):
        now = timezone.now()
        return [
            TaskRow(
                title="Publish scheduled articles",
                description="Every 5 minutes",
                schedule="Every 5 minutes",
                source="Blog",
                status=TaskStatus.SUCCESS,
                last_run_at=now - timedelta(minutes=2),
                next_run_at=now + timedelta(minutes=3),
                duration=1,
            ),
            TaskRow(
                title="Rebuild the sitemap",
                description="Every hour",
                schedule="Every hour",
                source="Blog",
                status=TaskStatus.RUNNING,
                last_run_at=now - timedelta(seconds=20),
            ),
            TaskRow(
                title="Send the newsletter",
                description="Mondays at 08:00",
                schedule="Mondays at 08:00",
                source="Blog",
                status=TaskStatus.FAILURE,
                last_run_at=now - timedelta(days=1),
                next_run_at=now + timedelta(days=6),
                duration=12,
                error_message="SMTP server refused the connection",
            ),
            TaskRow(
                title="Send the notification digest",
                description="Daily at 07:00",
                schedule="Daily at 07:00",
                source="Blog",
                status=TaskStatus.SUCCESS,
                last_run_at=now - timedelta(hours=2),
                next_run_at=now + timedelta(hours=22),
                duration=6,
            ),
            TaskRow(
                title="Prune old notifications",
                description="Sundays at 03:00",
                schedule="Sundays at 03:00",
                source="Blog",
                status=TaskStatus.SUCCESS,
                last_run_at=now - timedelta(days=2),
                next_run_at=now + timedelta(days=5),
                duration=2,
            ),
        ]

    def get_recent_tasks(self, request, limit):
        now = timezone.now()
        runs = [
            ("Make image sizes", "Alpine dawn", TaskStatus.SUCCESS, 1, 2),
            ("Deliver webhook", "Netlify deploy", TaskStatus.SUCCESS, 3, 0),
            ("Purge CDN cache", "/travel/slow-train", TaskStatus.SUCCESS, 4, 1),
            ("Send notification digest", "38 recipients", TaskStatus.SUCCESS, 9, 6),
            ("Make image sizes", "Desert dunes", TaskStatus.SUCCESS, 14, 3),
            ("Import reader reviews", "Feedback form", TaskStatus.FAILURE, 22, 4),
            ("Deliver webhook", "Search index", TaskStatus.SUCCESS, 31, 0),
            ("Rebuild the sitemap", "212 URLs", TaskStatus.SUCCESS, 58, 7),
            ("Publish scheduled articles", "1 article", TaskStatus.SUCCESS, 63, 1),
            ("Purge CDN cache", "/design/", TaskStatus.SUCCESS, 75, 1),
        ]
        return [
            TaskRow(
                title=title,
                description=description,
                status=status,
                source="Blog",
                last_run_at=now - timedelta(minutes=minutes),
                duration=duration,
                error_message=(
                    "The feedback form API answered 503"
                    if status == TaskStatus.FAILURE
                    else None
                ),
            )
            for title, description, status, minutes, duration in runs
        ][:limit]


# One adapter for the task dashboard and the status page.
demo_task_adapter = DemoTaskAdapter()
