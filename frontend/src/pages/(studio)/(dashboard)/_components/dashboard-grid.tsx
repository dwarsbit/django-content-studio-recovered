import { type ComponentType, Fragment } from "react";

import {
  ReviewQueueWidget,
  useReviewScene,
} from "@/components/review/review-mock";
import { cn } from "@/lib/utils";
import { type DashboardWidget, DashboardWidgetType } from "@/types";

import { ActivityLogWidget } from "./activity-log-widget";
import { ContentListWidget } from "./content-list-widget";
import { NotificationsWidget } from "./notifications-widget";
import { ScheduledTasksWidget } from "./scheduled-tasks-widget";
import { StatisticWidget } from "./statistic-widget";

const WIDGET_COMPONENTS: Partial<
  Record<DashboardWidgetType, ComponentType<{ widget: DashboardWidget }>>
> = {
  [DashboardWidgetType.ActivityLogWidget]: ActivityLogWidget,
  [DashboardWidgetType.StatisticWidget]: StatisticWidget,
  [DashboardWidgetType.ScheduledTasksWidget]: ScheduledTasksWidget,
  [DashboardWidgetType.ContentListWidget]: ContentListWidget,
  [DashboardWidgetType.NotificationsWidget]: NotificationsWidget,
};

// The grid has four columns at xl and two at md: a widget's `col_span`
// is clamped to the columns available, so wide widgets fill the row
// instead of overflowing it.
const COL_SPAN: Record<number, string> = {
  1: "",
  2: "md:col-span-2",
  3: "md:col-span-2 xl:col-span-3",
  4: "md:col-span-2 xl:col-span-4",
};

/**
 * A dashboard's widgets in a grid, shared by the start page and the
 * dashboard pages. Widgets without a display take no space.
 */
export function DashboardGrid({ widgets }: { widgets: DashboardWidget[] }) {
  // MOCK: the review queue widget.
  const scene = useReviewScene();

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 items-start">
      {widgets.map((widget, index) => {
        const Comp = widget.widget_type
          ? WIDGET_COMPONENTS[widget.widget_type]
          : undefined;
        const span = Math.min(Math.max(widget.col_span, 1), 4);

        const card = Comp ? (
          <div
            key={widget.widget_id}
            className={cn(
              "min-w-0",
              COL_SPAN[span],
              // Statistics in a row share one height.
              widget.widget_type === DashboardWidgetType.StatisticWidget &&
                "self-stretch",
            )}
          >
            <Comp widget={widget} />
          </div>
        ) : null;

        // MOCK: the review queue under the statistics.
        return scene === "dash" && index === 3 ? (
          <Fragment key={widget.widget_id}>
            {card}
            <div className="min-w-0 md:col-span-2 xl:col-span-4">
              <ReviewQueueWidget />
            </div>
          </Fragment>
        ) : (
          card
        );
      })}
    </div>
  );
}
