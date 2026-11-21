import { describe, expect, it } from "vitest";

import {
  arrangeColumns,
  BOARD_NONE,
  cardColumn,
  columnKey,
  saveValue,
  showParams,
} from "@/lib/board";
import type { BoardViewConfig, Resource } from "@/types";

const config: BoardViewConfig = {
  type: "board",
  key: "board:status",
  field: "status",
  label: "Status",
  relation: false,
  empty_value: "",
  columns: [],
  editable: true,
};
const relation: BoardViewConfig = {
  ...config,
  key: "board:author",
  field: "author",
  relation: true,
  empty_value: null,
};

const card = (id: string, fields: Record<string, unknown>) =>
  ({ id, __str__: id, ...fields }) as Resource;

describe("board", () => {
  it("keys columns by value, with one key for no value", () => {
    expect(columnKey("draft")).toBe("draft");
    expect(columnKey(3)).toBe("3");
    expect(columnKey(null)).toBe(BOARD_NONE);
    expect(columnKey("")).toBe(BOARD_NONE);
  });

  it("finds a card's column by its value or related id", () => {
    expect(cardColumn(card("1", { status: "draft" }), config)).toBe("draft");
    expect(cardColumn(card("1", { status: "" }), config)).toBe(BOARD_NONE);
    expect(
      cardColumn(card("1", { author: { id: 7, __str__: "Ada" } }), relation),
    ).toBe("7");
    expect(cardColumn(card("1", { author: null }), relation)).toBe(BOARD_NONE);
  });

  it("saves a column's value as the field takes it", () => {
    expect(saveValue(config, "published")).toBe("published");
    expect(saveValue(config, null)).toBe("");
    expect(saveValue(relation, 7)).toEqual({ id: 7 });
    expect(saveValue(relation, null)).toBeNull();
  });

  it("moves dropped cards and their counts", () => {
    const a = card("a", { status: "draft" });
    const b = card("b", { status: "draft" });
    const c = card("c", { status: "published" });
    const columns = [
      { value: "draft", label: "Draft", count: 5, results: [a, b] },
      { value: "published", label: "Published", count: 1, results: [c] },
    ];

    const arranged = arrangeColumns(columns, {
      a: { item: a, from: "draft", to: "published" },
    });

    expect(arranged[0].results.map((item) => item.id)).toEqual(["b"]);
    expect(arranged[0].count).toBe(4);
    expect(arranged[1].results.map((item) => item.id)).toEqual(["a", "c"]);
    expect(arranged[1].count).toBe(2);
  });

  it("does not count a moved card twice once the board refreshed", () => {
    const a = card("a", { status: "published" });
    const columns = [
      { value: "draft", label: "Draft", count: 0, results: [] },
      { value: "published", label: "Published", count: 1, results: [a] },
    ];

    const arranged = arrangeColumns(columns, {
      a: { item: a, from: "draft", to: "published" },
    });

    expect(arranged[0].count).toBe(0);
    expect(arranged[1].count).toBe(1);
    expect(arranged[1].results).toHaveLength(1);
  });

  it("asks for more cards per column", () => {
    expect(showParams({ draft: 40, [BOARD_NONE]: 60 })).toEqual([
      ["show", "draft:40"],
      ["show", `${BOARD_NONE}:60`],
    ]);
  });
});
