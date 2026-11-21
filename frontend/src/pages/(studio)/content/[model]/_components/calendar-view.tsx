import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import dayjs, { type Dayjs } from "dayjs";
import * as R from "ramda";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiCalendarBlankBold,
  PiCaretLeftBold,
  PiCaretRightBold,
  PiImage,
  PiSidebarSimpleBold,
  PiWarningBold,
} from "react-icons/pi";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { PublishingBadge } from "@/components/publishing/publishing-badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Spinner } from "@/components/ui/spinner";
import { useHttp } from "@/hooks/use-http";
import { useMediaQuery } from "@/hooks/use-media-query";
import {
  calendarLocale,
  dayKey,
  firstDayOfWeek,
  gridRange,
  itemDays,
  monthGrid,
  moveToDay,
  shiftBy,
} from "@/lib/calendar";
import { safeStorage } from "@/lib/safe-storage";
import { cn } from "@/lib/utils";
import type {
  CalendarViewConfig,
  Model,
  PublishingState,
  Resource,
} from "@/types";

// The chips a day shows before "+N more".
const MAX_PER_DAY = 3;

// The tray's drop target id.
const TRAY = "__tray__";

const DOTS: Record<PublishingState, string> = {
  draft: "bg-muted-foreground/60",
  scheduled: "bg-blue-500",
  published: "bg-green-500",
  expired: "bg-amber-500",
};

interface CalendarResponse {
  results: Resource[];
  truncated: boolean;
  count?: number;
}

/**
 * The calendar view: the list's objects on a month grid by a date
 * field, with the list's search and filters. Items without a date wait
 * in a tray. Dragging an item to another day saves its new date at once
 * (rescheduling, for the publishing date) and offers Undo.
 */
export function CalendarView({
  model,
  config,
  params,
  className,
}: {
  model: Model;
  config: CalendarViewConfig;
  // The list's search and filters.
  params: Record<string, string | undefined>;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const http = useHttp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const narrow = useMediaQuery("(max-width: 639px)");
  const [searchParams, setSearchParams] = useSearchParams();
  const month = parseMonth(searchParams.get("month"));
  const locale = calendarLocale(i18n.language);
  const days = monthGrid(month, firstDayOfWeek(locale));
  const range = gridRange(days, config.date_only);
  const trayStorageKey = `__dcs_calendar_tray__:${model.label}`;
  const [trayOpen, setTrayOpenState] = useState(
    () => safeStorage.get(trayStorageKey) !== "closed",
  );
  // Dates shown in place of the saved ones while a drop saves.
  const [moved, setMoved] = useState<Record<string, string | null>>({});
  const [active, setActive] = useState<Resource | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor),
  );
  const publishing = model.admin.list.publishing;
  const showTray = config.nullable;

  const setMonth = (next: Dayjs | null) =>
    setSearchParams((searchParams) => {
      if (next && !next.isSame(dayjs(), "month")) {
        searchParams.set("month", next.format("YYYY-MM"));
      } else {
        searchParams.delete("month");
      }
      return searchParams;
    });

  const setTrayOpen = (open: boolean) => {
    setTrayOpenState(open);
    safeStorage.set(trayStorageKey, open ? "open" : "closed");
  };

  const queryKey = [
    "resources",
    model.label,
    "calendar",
    config.key,
    { range, params },
  ];
  const { data, isFetching } = useQuery({
    queryKey,
    placeholderData: (previous) => previous,
    async queryFn() {
      const { data } = await http.get<CalendarResponse>(
        `/content/${model.label}/calendar`,
        { params: { ...params, view: config.key, ...range } },
      );
      return data;
    },
  });
  const { data: tray } = useQuery({
    queryKey: [
      "resources",
      model.label,
      "calendar",
      config.key,
      "tray",
      params,
    ],
    enabled: showTray,
    async queryFn() {
      const { data } = await http.get<CalendarResponse>(
        `/content/${model.label}/calendar`,
        { params: { ...params, view: config.key, unscheduled: 1 } },
      );
      return data;
    },
  });

  const items = R.uniqBy(
    (item) => String(item.id),
    [...(data?.results ?? []), ...(tray?.results ?? [])],
  );
  const dateOf = (item: Resource) =>
    String(item.id) in moved
      ? moved[String(item.id)]
      : ((item[config.field] as string | null | undefined) ?? null);
  const endOf = (item: Resource) =>
    config.end
      ? ((item[config.end] as string | null | undefined) ?? null)
      : null;
  const stateOf = (item: Resource): PublishingState | null => {
    if (!config.publishing) {
      return item.__publishing__?.state ?? null;
    }
    if (String(item.id) in moved) {
      return moved[String(item.id)] ? "scheduled" : "draft";
    }
    return item.__publishing__?.state ?? null;
  };

  // Whether the editor may drag this item: scheduled and draft items of
  // the publishing date (published ones already went live), any item
  // they may change otherwise.
  const draggable = (item: Resource) => {
    if (!config.editable) {
      return false;
    }
    if (config.publishing) {
      const state = stateOf(item);
      return state === "scheduled" || state === "draft";
    }
    return item.__can_change__ !== false;
  };
  // The publishing date only moves into the future.
  const droppable = (day: Dayjs) =>
    !config.publishing || !day.isBefore(dayjs(), "day");

  const byDay: Record<string, Resource[]> = {};
  const undated: Resource[] = [];

  for (const item of items) {
    const date = dateOf(item);
    if (!date) {
      undated.push(item);
      continue;
    }
    for (const key of itemDays(date, endOf(item))) {
      (byDay[key] ??= []).push(item);
    }
  }
  for (const list of Object.values(byDay)) {
    list.sort(
      (a, b) => dayjs(dateOf(a)).valueOf() - dayjs(dateOf(b)).valueOf(),
    );
  }

  const open = (item: Resource) =>
    navigate(`/content/${model.label}/${item.id}`);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["resources", model.label] });

  // Saves an item's date: through the publishing endpoint for the
  // publishing date, else as a table edit (with the shown value as its
  // base, so someone else's change is not overwritten).
  const saveDate = async (
    item: Resource,
    next: string | null,
    previous: string | null,
  ) => {
    if (config.publishing) {
      await http.post(`/content/${model.label}/${item.id}/publishing`, {
        action: next ? "schedule" : "unpublish",
        ...(next ? { at: next } : {}),
      });
      return;
    }

    const values: Record<string, unknown> = { [config.field]: next };
    const base: Record<string, unknown> = { [config.field]: previous };

    if (config.end && next) {
      values[config.end] = shiftBy(
        endOf(item),
        previous,
        next,
        config.date_only,
      );
      base[config.end] = endOf(item);
    }

    await http.post(`/content/${model.label}/${item.id}/table-edit`, {
      values,
      base,
    });
  };

  const move = async (item: Resource, next: string | null) => {
    const id = String(item.id);
    const previous = dateOf(item);

    if (next === previous) {
      return;
    }

    setMoved((current) => ({ ...current, [id]: next }));

    try {
      await saveDate(item, next, previous);
      await refresh();
      toast.success(
        next
          ? t(
              previous
                ? "list_view.calendar.moved"
                : "list_view.calendar.dated",
            )
          : t("list_view.calendar.undated"),
        {
          description: next
            ? `${item.__str__} · ${formatWhen(next, config.date_only)}`
            : item.__str__,
          action: {
            label: t("table_edit.undo"),
            onClick: () => void undo(item, previous, next),
          },
        },
      );
    } catch (error) {
      toast.error(errorMessage(error, t("table_edit.failed")));
      void refresh();
    } finally {
      setMoved((current) => R.omit([id], current));
    }
  };

  const undo = async (
    item: Resource,
    previous: string | null,
    next: string | null,
  ) => {
    try {
      await saveDate(
        {
          ...item,
          [config.field]: next,
          ...(config.end
            ? {
                [config.end]: shiftBy(
                  endOf(item),
                  previous,
                  next ?? previous ?? "",
                  config.date_only,
                ),
              }
            : {}),
        },
        previous,
        next,
      );
    } catch (error) {
      toast.error(errorMessage(error, t("table_edit.failed")));
    }
    void refresh();
  };

  const legend = publishing
    ? (["draft", "scheduled", "published", "expired"] as const)
    : [];

  if (narrow) {
    return (
      <CalendarAgenda
        days={days.filter((day) => day.isSame(month, "month"))}
        byDay={byDay}
        undated={showTray ? undated : []}
        month={month}
        onMonth={setMonth}
        dateOf={dateOf}
        stateOf={stateOf}
        dateOnly={config.date_only}
        onOpen={open}
      />
    );
  }

  return (
    <DndContext
      sensors={sensors}
      autoScroll={false}
      onDragStart={(event) =>
        setActive(items.find((i) => String(i.id) === event.active.id) ?? null)
      }
      onDragCancel={() => setActive(null)}
      onDragEnd={(event) => {
        setActive(null);
        const item = items.find((i) => String(i.id) === event.active.id);

        if (!item || !event.over) {
          return;
        }

        const target = String(event.over.id);
        void move(
          item,
          target === TRAY
            ? null
            : moveToDay(dateOf(item), target, config.date_only),
        );
      }}
    >
      <div className={cn("flex flex-col w-full", className)}>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b">
          <Button variant="outline" size="sm" onClick={() => setMonth(null)}>
            {t("list_view.calendar.today")}
          </Button>
          <div className="flex items-center">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("list_view.calendar.previous")}
              title={t("list_view.calendar.previous")}
              onClick={() => setMonth(month.subtract(1, "month"))}
            >
              <PiCaretLeftBold />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("list_view.calendar.next")}
              title={t("list_view.calendar.next")}
              onClick={() => setMonth(month.add(1, "month"))}
            >
              <PiCaretRightBold />
            </Button>
          </div>
          <h2 className="text-base font-semibold capitalize">
            {month.toDate().toLocaleDateString(calendarLocale(i18n.language), {
              month: "long",
              year: "numeric",
            })}
          </h2>
          {isFetching && <Spinner className="size-4 text-muted-foreground" />}
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            {legend.map((state) => (
              <span
                key={state}
                className="hidden xl:inline-flex items-center gap-1.5"
              >
                <span className={cn("size-2 rounded-full", DOTS[state])} />
                {t(`publishing.states.${state}`)}
              </span>
            ))}
            {showTray && (
              <Button
                variant={trayOpen ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={trayOpen}
                onClick={() => setTrayOpen(!trayOpen)}
              >
                <PiSidebarSimpleBold className="-scale-x-100" />
                {t("list_view.calendar.undated_title")}
                <span className="tabular-nums text-muted-foreground">
                  {tray?.count ?? undated.length}
                </span>
              </Button>
            )}
          </div>
        </div>
        {data?.truncated && (
          <p className="flex items-center gap-2 px-4 py-2 border-b text-xs text-muted-foreground bg-muted/40">
            <PiWarningBold className="shrink-0" />
            {t("list_view.calendar.truncated", { count: data.results.length })}
          </p>
        )}
        <div className="flex">
          <div className="flex-1 min-w-0">
            <div className="grid grid-cols-7 border-b text-xs font-medium text-muted-foreground">
              {days.slice(0, 7).map((day) => (
                <div key={dayKey(day)} className="px-2 py-1.5 truncate">
                  {day
                    .toDate()
                    .toLocaleDateString(calendarLocale(i18n.language), {
                      weekday: "short",
                    })}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7" role="grid">
              {days.map((day, index) => {
                const key = dayKey(day);
                return (
                  <CalendarDay
                    key={key}
                    day={day}
                    inMonth={day.isSame(month, "month")}
                    lastColumn={index % 7 === 6}
                    lastRow={index >= days.length - 7}
                    droppable={droppable(day)}
                    items={byDay[key] ?? []}
                    renderChip={(item) => (
                      <CalendarChip
                        key={item.id}
                        item={item}
                        state={stateOf(item)}
                        date={dateOf(item)}
                        dateOnly={config.date_only}
                        draggable={draggable(item)}
                        dragging={String(active?.id) === String(item.id)}
                        onOpen={() => open(item)}
                      />
                    )}
                  />
                );
              })}
            </div>
          </div>
          {showTray && trayOpen && (
            <CalendarTray
              items={undated}
              total={tray?.count ?? undated.length}
              publishing={config.publishing}
              editable={config.editable}
              draggable={draggable}
              activeId={active ? String(active.id) : null}
              onOpen={open}
            />
          )}
        </div>
      </div>
      <DragOverlay dropAnimation={null}>
        {active && (
          <div className="w-48 rotate-1">
            <ChipBody
              item={active}
              state={stateOf(active)}
              date={dateOf(active)}
              dateOnly={config.date_only}
              className="shadow-lg ring-1 ring-border bg-card cursor-grabbing"
            />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function CalendarDay({
  day,
  inMonth,
  lastColumn,
  lastRow,
  droppable,
  items,
  renderChip,
}: {
  day: Dayjs;
  inMonth: boolean;
  lastColumn: boolean;
  lastRow: boolean;
  droppable: boolean;
  items: Resource[];
  renderChip(item: Resource): React.ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({
    id: dayKey(day),
    disabled: !droppable,
  });
  const today = day.isSame(dayjs(), "day");
  const shown = items.slice(0, MAX_PER_DAY);
  const more = items.length - shown.length;

  return (
    <div
      ref={setNodeRef}
      role="gridcell"
      aria-label={day
        .toDate()
        .toLocaleDateString(calendarLocale(i18n.language), {
          dateStyle: "full",
        })}
      data-day={dayKey(day)}
      className={cn(
        "min-h-28 min-w-0 p-1.5 flex flex-col gap-1 border-b border-r",
        lastColumn && "border-r-0",
        lastRow && "border-b-0",
        !inMonth && "bg-muted/40",
        isOver && "bg-accent ring-2 ring-inset ring-ring/60",
      )}
    >
      <span
        className={cn(
          "self-start text-xs tabular-nums size-6 flex items-center justify-center rounded-full",
          inMonth ? "text-foreground" : "text-muted-foreground/70",
          today && "bg-primary text-primary-foreground font-semibold",
        )}
      >
        {day.date()}
      </span>
      {shown.map(renderChip)}
      {more > 0 && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="self-start text-xs font-medium text-muted-foreground hover:text-foreground px-1.5 rounded"
            >
              {t("list_view.calendar.more", { count: more })}
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-64 p-2">
            <p className="px-1 pb-1.5 text-xs font-medium text-muted-foreground">
              {day.toDate().toLocaleDateString(calendarLocale(i18n.language), {
                weekday: "long",
                day: "numeric",
                month: "long",
              })}
            </p>
            <div className="flex flex-col gap-1">{items.map(renderChip)}</div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

function CalendarChip({
  item,
  state,
  date,
  dateOnly,
  draggable,
  dragging,
  onOpen,
}: {
  item: Resource;
  state: PublishingState | null;
  date: string | null;
  dateOnly: boolean;
  draggable: boolean;
  dragging: boolean;
  onOpen(): void;
}) {
  const { setNodeRef, listeners, attributes } = useDraggable({
    id: String(item.id),
    disabled: !draggable,
  });

  return (
    <button
      ref={setNodeRef}
      type="button"
      {...attributes}
      {...listeners}
      onClick={onOpen}
      className={cn(
        "block w-full text-left rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        draggable && "cursor-grab",
        dragging && "opacity-40",
      )}
    >
      <ChipBody item={item} state={state} date={date} dateOnly={dateOnly} />
    </button>
  );
}

function ChipBody({
  item,
  state,
  date,
  dateOnly,
  className,
}: {
  item: Resource;
  state: PublishingState | null;
  date: string | null;
  dateOnly: boolean;
  className?: string;
}) {
  const title = item.list_item_display?.title || item.__str__;

  return (
    <span
      title={date ? `${title} · ${formatWhen(date, dateOnly)}` : String(title)}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs select-none",
        state === "scheduled"
          ? "bg-blue-500/10 text-blue-950 dark:text-blue-100 hover:bg-blue-500/15"
          : "bg-muted hover:bg-accent",
        className,
      )}
    >
      {state && (
        <span className={cn("size-1.5 shrink-0 rounded-full", DOTS[state])} />
      )}
      {date && !dateOnly && (
        <span className="tabular-nums text-muted-foreground shrink-0">
          {dayjs(date).format("HH:mm")}
        </span>
      )}
      <span className="truncate font-medium">{title}</span>
    </span>
  );
}

function CalendarTray({
  items,
  total,
  publishing,
  editable,
  draggable,
  activeId,
  onOpen,
}: {
  items: Resource[];
  total: number;
  publishing: boolean;
  editable: boolean;
  draggable(item: Resource): boolean;
  activeId: string | null;
  onOpen(item: Resource): void;
}) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({
    id: TRAY,
    disabled: !editable,
  });

  return (
    <aside
      ref={setNodeRef}
      aria-label={t("list_view.calendar.undated_title")}
      className={cn(
        "w-56 shrink-0 border-l bg-muted/30 flex flex-col transition-colors",
        isOver && "bg-accent",
      )}
    >
      <div className="px-3 pt-3 pb-1 text-xs font-medium text-muted-foreground">
        {t("list_view.calendar.undated_heading")}
      </div>
      <div className="flex flex-col gap-2 p-3 pt-1">
        {items.map((item) => (
          <TrayCard
            key={item.id}
            item={item}
            publishing={publishing}
            draggable={draggable(item)}
            dragging={activeId === String(item.id)}
            onOpen={() => onOpen(item)}
          />
        ))}
        {total > items.length && (
          <p className="text-xs text-muted-foreground px-1">
            {t("list_view.calendar.undated_more", {
              count: total - items.length,
            })}
          </p>
        )}
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground py-6 text-center">
            {t("list_view.calendar.undated_empty")}
          </p>
        )}
      </div>
      {editable && (
        <p className="mt-auto flex items-start gap-1.5 p-3 text-xs text-muted-foreground border-t">
          <PiCalendarBlankBold className="mt-0.5 shrink-0" />
          {t(
            publishing
              ? "list_view.calendar.hint_schedule"
              : "list_view.calendar.hint_date",
          )}
        </p>
      )}
    </aside>
  );
}

function TrayCard({
  item,
  publishing,
  draggable,
  dragging,
  onOpen,
}: {
  item: Resource;
  publishing: boolean;
  draggable: boolean;
  dragging: boolean;
  onOpen(): void;
}) {
  const { setNodeRef, listeners, attributes } = useDraggable({
    id: String(item.id),
    disabled: !draggable,
  });
  const thumbnail = item.list_item_display?.thumbnail;

  return (
    <button
      ref={setNodeRef}
      type="button"
      {...attributes}
      {...listeners}
      onClick={onOpen}
      className={cn(
        "flex items-center gap-2.5 rounded-md border bg-card p-2 text-left hover:bg-muted select-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        draggable && "cursor-grab",
        dragging && "opacity-40",
      )}
    >
      {thumbnail !== undefined && (
        <span className="size-9 shrink-0 rounded overflow-hidden bg-muted flex items-center justify-center">
          {thumbnail ? (
            <img src={thumbnail} alt="" className="size-full object-cover" />
          ) : (
            <PiImage className="text-muted-foreground" />
          )}
        </span>
      )}
      <span className="min-w-0 flex flex-col gap-1">
        <span className="text-xs font-medium line-clamp-2">
          {item.list_item_display?.title || item.__str__}
        </span>
        {publishing && <PublishingBadge state="draft" className="self-start" />}
      </span>
    </button>
  );
}

/**
 * Narrow screens: the month as a list of the days that have items,
 * with the undated items at the end. Dragging is left to wider screens.
 */
function CalendarAgenda({
  days,
  byDay,
  undated,
  month,
  onMonth,
  dateOf,
  stateOf,
  dateOnly,
  onOpen,
}: {
  days: Dayjs[];
  byDay: Record<string, Resource[]>;
  undated: Resource[];
  month: Dayjs;
  onMonth(month: Dayjs | null): void;
  dateOf(item: Resource): string | null;
  stateOf(item: Resource): PublishingState | null;
  dateOnly: boolean;
  onOpen(item: Resource): void;
}) {
  const { t, i18n } = useTranslation();
  const busy = days.filter((day) => byDay[dayKey(day)]?.length);
  const row = (item: Resource) => (
    <button
      key={item.id}
      type="button"
      onClick={() => onOpen(item)}
      className="block w-full text-left"
    >
      <ChipBody
        item={item}
        state={stateOf(item)}
        date={dateOf(item)}
        dateOnly={dateOnly}
        className="py-2 text-sm"
      />
    </button>
  );

  return (
    <div className="flex flex-col w-full">
      <div className="flex items-center gap-1 px-3 py-2 border-b">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t("list_view.calendar.previous")}
          onClick={() => onMonth(month.subtract(1, "month"))}
        >
          <PiCaretLeftBold />
        </Button>
        <h2 className="flex-1 text-center text-sm font-semibold capitalize">
          {month.toDate().toLocaleDateString(calendarLocale(i18n.language), {
            month: "long",
            year: "numeric",
          })}
        </h2>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t("list_view.calendar.next")}
          onClick={() => onMonth(month.add(1, "month"))}
        >
          <PiCaretRightBold />
        </Button>
      </div>
      {busy.map((day) => (
        <section key={dayKey(day)} className="px-3 py-2 border-b">
          <h3
            className={cn(
              "text-xs font-medium text-muted-foreground pb-1.5",
              day.isSame(dayjs(), "day") && "text-foreground",
            )}
          >
            {day.toDate().toLocaleDateString(calendarLocale(i18n.language), {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </h3>
          <div className="flex flex-col gap-1">
            {byDay[dayKey(day)].map(row)}
          </div>
        </section>
      ))}
      {busy.length === 0 && (
        <p className="px-3 py-8 text-center text-sm text-muted-foreground">
          {t("list_view.calendar.empty_month")}
        </p>
      )}
      {undated.length > 0 && (
        <section className="px-3 py-2">
          <h3 className="text-xs font-medium text-muted-foreground pb-1.5">
            {t("list_view.calendar.undated_heading")}
          </h3>
          <div className="flex flex-col gap-1">{undated.map(row)}</div>
        </section>
      )}
    </div>
  );
}

function parseMonth(value: string | null): Dayjs {
  const parsed =
    value && /^\d{4}-\d{2}$/.test(value) ? dayjs(`${value}-01`) : null;

  return (parsed?.isValid() ? parsed : dayjs()).startOf("month");
}

function formatWhen(value: string, dateOnly: boolean) {
  return dayjs(value).format(dateOnly ? "ddd D MMM" : "ddd D MMM, HH:mm");
}

function errorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error) || !error.response) {
    return fallback;
  }

  const data = error.response.data as Record<string, unknown> | undefined;
  const source =
    error.response.status === 409
      ? Object.values((data?.conflicts as Record<string, unknown>) ?? {})
      : Object.values(data ?? {});
  const message = source
    .flatMap((entry) => (Array.isArray(entry) ? entry : [entry]))
    .find((entry) => typeof entry === "string");

  return typeof message === "string" ? message : fallback;
}
