import dayjs from "dayjs";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  calendarLocale,
  dayKey,
  gridRange,
  itemDays,
  monthGrid,
  moveToDay,
  shiftBy,
} from "@/lib/calendar";

describe("monthGrid", () => {
  const november = dayjs("2026-11-01");

  it("shows whole weeks from the locale's first weekday", () => {
    const monday = monthGrid(november, 1);

    expect(dayKey(monday[0])).toBe("2026-10-26");
    expect(dayKey(monday.at(-1)!)).toBe("2026-12-06");
    expect(monday).toHaveLength(42);
  });

  it("starts on the 1st when it is the first weekday", () => {
    // 1 November 2026 is a Sunday.
    const sunday = monthGrid(november, 0);

    expect(dayKey(sunday[0])).toBe("2026-11-01");
    expect(dayKey(sunday.at(-1)!)).toBe("2026-12-05");
    expect(sunday).toHaveLength(35);
  });
});

describe("itemDays", () => {
  it("is the item's day, or every day of its span", () => {
    expect(itemDays(null)).toEqual([]);
    expect(itemDays("2026-11-03")).toEqual(["2026-11-03"]);
    expect(itemDays("2026-11-29", "2026-12-02")).toEqual([
      "2026-11-29",
      "2026-11-30",
      "2026-12-01",
      "2026-12-02",
    ]);
  });

  it("caps a runaway span", () => {
    expect(itemDays("2026-01-01", "2030-01-01")).toHaveLength(62);
  });

  it("ignores an end before the start", () => {
    expect(itemDays("2026-11-03", "2026-11-01")).toEqual(["2026-11-03"]);
  });
});

describe("moveToDay", () => {
  it("keeps the time of a date-time", () => {
    const moved = moveToDay(
      new Date(2026, 10, 3, 14, 30).toISOString(),
      "2026-11-12",
      false,
    );

    expect(dayjs(moved).format("YYYY-MM-DD HH:mm")).toBe("2026-11-12 14:30");
  });

  it("starts an undated item at nine", () => {
    expect(
      dayjs(moveToDay(null, "2026-11-12", false)).format("YYYY-MM-DD HH:mm"),
    ).toBe("2026-11-12 09:00");
  });

  it("gives a date field the day", () => {
    expect(moveToDay("2026-11-03", "2026-11-12", true)).toBe("2026-11-12");
  });
});

describe("shiftBy", () => {
  it("moves an end date along with its start", () => {
    expect(shiftBy("2026-11-05", "2026-11-03", "2026-11-10", true)).toBe(
      "2026-11-12",
    );
    expect(shiftBy(null, "2026-11-03", "2026-11-10", true)).toBeNull();
  });
});

describe("gridRange", () => {
  const days = monthGrid(dayjs("2026-11-01"), 1);

  it("bounds a date field by days, the last one excluded", () => {
    expect(gridRange(days, true)).toEqual({
      from: "2026-10-26",
      to: "2026-12-07",
    });
  });

  it("bounds a date-time field by local midnights", () => {
    const { from, to } = gridRange(days, false);

    expect(new Date(from).getTime()).toBe(new Date(2026, 9, 26).getTime());
    expect(new Date(to).getTime()).toBe(new Date(2026, 11, 7).getTime());
  });
});

describe("calendarLocale", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("follows the browser when it speaks the admin's language", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["en-GB"]);

    expect(calendarLocale("en")).toBe("en-GB");
    expect(calendarLocale("nl")).toBe("nl");
  });
});
