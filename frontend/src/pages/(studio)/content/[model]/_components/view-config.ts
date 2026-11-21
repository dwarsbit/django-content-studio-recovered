import type { CalendarViewConfig, ListViewConfig } from "@/types";

/** A view's key in the view switch: its name, or a calendar's key. */
export const viewKey = (view: ListViewConfig) =>
  typeof view === "string" ? view : view.key;

/** The calendar with the given key, if the view is one. */
export function findCalendar(
  views: ListViewConfig[],
  key: string,
): CalendarViewConfig | undefined {
  return views.find(
    (view): view is CalendarViewConfig =>
      typeof view !== "string" && view.type === "calendar" && view.key === key,
  );
}
