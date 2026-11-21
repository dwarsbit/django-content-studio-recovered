import dayjs, { type Dayjs } from "dayjs";

// The longest span an item is drawn across, in days: a longer one (a
// typo in an end date) would fill every cell.
const MAX_SPAN_DAYS = 62;

/** A day's key: YYYY-MM-DD in local time. */
export const dayKey = (day: Dayjs) => day.format("YYYY-MM-DD");

/**
 * The locale a calendar follows: the browser's own when it speaks the
 * admin's language (en-GB for "en"), so weeks start and dates read as
 * the editor is used to; else the admin's language.
 */
export function calendarLocale(language: string): string {
  const browser =
    typeof navigator !== "undefined" ? navigator.languages?.[0] : undefined;
  const base = (tag: string) => tag.toLowerCase().split("-")[0];

  return browser && base(browser) === base(language) ? browser : language;
}

/**
 * The first day of the week for a locale, 0 = Sunday … 6 = Saturday;
 * Monday when the browser does not know.
 */
export function firstDayOfWeek(locale: string): number {
  try {
    const info =
      (
        new Intl.Locale(locale) as Intl.Locale & {
          getWeekInfo?: () => { firstDay: number };
          weekInfo?: { firstDay: number };
        }
      ).getWeekInfo?.() ??
      (new Intl.Locale(locale) as { weekInfo?: { firstDay: number } }).weekInfo;

    // Intl counts 1 = Monday … 7 = Sunday.
    return info ? info.firstDay % 7 : 1;
  } catch {
    return 1;
  }
}

/**
 * The days a month grid shows: whole weeks from the week of the 1st
 * through the week of the last day (5 or 6 weeks).
 */
export function monthGrid(month: Dayjs, weekStart: number): Dayjs[] {
  const first = month.startOf("month");
  const start = first.subtract((first.day() - weekStart + 7) % 7, "day");
  const last = month.endOf("month");
  const days: Dayjs[] = [];

  for (let day = start; day.isBefore(last) || days.length % 7 !== 0;) {
    days.push(day);
    day = day.add(1, "day");
  }

  return days;
}

/**
 * The day keys an item shows on: its date, or every day from its date
 * through its end. Empty without a date.
 */
export function itemDays(
  start: string | null | undefined,
  end?: string | null,
): string[] {
  if (!start) {
    return [];
  }

  const from = dayjs(start).startOf("day");
  const until = end ? dayjs(end).startOf("day") : from;
  const days = [dayKey(from)];

  for (
    let day = from.add(1, "day");
    !day.isAfter(until) && days.length < MAX_SPAN_DAYS;
    day = day.add(1, "day")
  ) {
    days.push(dayKey(day));
  }

  return days;
}

/**
 * An item's date moved to another day, keeping its time: a date for a
 * DateField, an ISO date-time otherwise. Without a date yet, a moved
 * date-time starts at 09:00.
 */
export function moveToDay(
  value: string | null | undefined,
  day: string,
  dateOnly: boolean,
): string {
  if (dateOnly) {
    return day;
  }

  const time = value ? dayjs(value) : dayjs().hour(9).minute(0);

  return dayjs(day)
    .hour(time.hour())
    .minute(time.minute())
    .second(0)
    .millisecond(0)
    .toISOString();
}

/** A date shifted by the days between two values, in the same form. */
export function shiftBy(
  value: string | null | undefined,
  from: string | null | undefined,
  to: string,
  dateOnly: boolean,
): string | null {
  if (!value) {
    return value ?? null;
  }

  const days = dayjs(to)
    .startOf("day")
    .diff(dayjs(from ?? to).startOf("day"), "day");
  const shifted = dayjs(value).add(days, "day");

  return dateOnly ? dayKey(shifted) : shifted.toISOString();
}

/** The bounds of a grid for the calendar endpoint: [from, to). */
export function gridRange(days: Dayjs[], dateOnly: boolean) {
  const from = days[0].startOf("day");
  const to = days[days.length - 1].add(1, "day").startOf("day");

  return dateOnly
    ? { from: dayKey(from), to: dayKey(to) }
    : { from: from.toISOString(), to: to.toISOString() };
}
