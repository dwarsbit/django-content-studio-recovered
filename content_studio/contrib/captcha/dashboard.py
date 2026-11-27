"""
The captcha on a dashboard: how many challenges the widget solved over a
range, with the failed ones in the footnote. Add it to the site's
dashboard yourself.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from content_studio.dashboard.statistic import (
    StatisticWidget,
    StatisticWidgetSerializer,
)

from . import counts

__all__ = ["CaptchaStatisticWidget"]

# The ranges, in days; the title names them like the task statistics ("30d").
RANGES = {"7d": 7, "30d": 30, "90d": 90}


class CaptchaStatisticWidget(StatisticWidget):
    """
    The challenges the captcha widget solved over a range (today
    included), with the change against the period before, a sparkline per
    day and the failed attempts in the footnote: wrong answers, and
    challenges that were unknown or had expired.
    """

    name = "CaptchaStatisticWidget"
    refresh_interval = 300

    def __init__(self, range="30d", title=None, widget_id=None):
        if range not in RANGES:
            raise ValueError(
                f"Unknown captcha range {range!r}; choose from {', '.join(RANGES)}."
            )

        self.range = range
        self.title = title
        super().__init__(widget_id)

    def get_id_parts(self) -> tuple[Any, ...]:
        return (self.name, self.range)

    def get_data(self, request) -> Any:
        days = RANGES[self.range]
        end = timezone.localdate()
        start = end - timedelta(days=days - 1)
        previous_start = start - timedelta(days=days)

        series = counts.daily("solved", start, end)
        solved = sum(series)
        failed = sum(counts.daily("failed", start, end))
        previous = sum(
            counts.daily("solved", previous_start, start - timedelta(days=1))
        )

        data: dict[str, Any] = {
            "title": f"{self.title or _('Captcha solves')} ({self.range})",
            "value": solved,
            "icon": "ph-bold ph-shield-check",
            "series": series,
            "footnote": self.failed_text(solved, failed),
        }

        if previous:
            trend = (solved - previous) / previous * 100
            data["trend"] = round(Decimal(str(trend)), 1)
            data["trend_label"] = str(_("vs. the period before"))

        return StatisticWidgetSerializer(data=data)

    @staticmethod
    def failed_text(solved: int, failed: int) -> str:
        text = ngettext("%(count)d failed", "%(count)d failed", failed) % {
            "count": failed
        }

        if failed:
            share = round(failed / (solved + failed) * 100)
            text = f"{text} ({share}%)"

        return text
