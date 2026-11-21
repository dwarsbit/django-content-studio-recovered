import type { BoardViewConfig, Resource } from "@/types";

// The cards a column shows at first, and adds with "Show more".
export const BOARD_PAGE_SIZE = 20;

// The key of the column of items without a value, in requests and as
// a drop target.
export const BOARD_NONE = "__none__";

/** A column's key: its value as a string, or BOARD_NONE. */
export const columnKey = (value: string | number | null | undefined) =>
  value === null || value === undefined || value === ""
    ? BOARD_NONE
    : String(value);

/** The key of the column a row belongs in, by its board field. */
export function cardColumn(item: Resource, config: BoardViewConfig): string {
  const value = item[config.field] as unknown;

  if (config.relation) {
    return columnKey(
      value && typeof value === "object"
        ? ((value as { id?: string | number }).id ?? null)
        : null,
    );
  }

  return columnKey(value as string | number | null);
}

/** What a save sends for a column: {"id"} for a relation, the empty
 * value for the column without one. */
export function saveValue(
  config: BoardViewConfig,
  value: string | number | null,
): unknown {
  if (value === null) {
    return config.relation ? null : config.empty_value;
  }

  return config.relation ? { id: value } : value;
}

export interface BoardColumnData {
  value: string | number | null;
  label: string;
  count: number;
  results: Resource[];
}

/** A card moved by a drop that is still saving (or just saved). */
export interface MovedCard {
  item: Resource;
  from: string;
  to: string;
}

/**
 * The columns as the board draws them: cards moved by a drop leave
 * their column and lead the one they were dropped on, and the counts
 * follow.
 */
export function arrangeColumns(
  columns: BoardColumnData[],
  moved: Record<string, MovedCard>,
): BoardColumnData[] {
  const moves = Object.values(moved);

  return columns.map((column) => {
    const key = columnKey(column.value);
    const incoming = moves.filter((move) => move.to === key);
    const outgoing = moves.filter((move) => move.from === key);
    const movedIds = new Set(moves.map((move) => String(move.item.id)));
    const stays = column.results.filter(
      (item) => !movedIds.has(String(item.id)),
    );
    // A card already in the results (the save refreshed the board
    // before the move was cleared) is not counted twice.
    const listed = new Set(column.results.map((item) => String(item.id)));

    return {
      ...column,
      count:
        column.count +
        incoming.filter((move) => !listed.has(String(move.item.id))).length -
        outgoing.filter((move) => listed.has(String(move.item.id))).length,
      results: [...incoming.map((move) => move.item), ...stays],
    };
  });
}

/** The "Show more" parameters: show=<column>:<cards>, repeated. */
export function showParams(shown: Record<string, number>): [string, string][] {
  return Object.entries(shown).map(([key, count]) => [
    "show",
    `${key}:${count}`,
  ]);
}
