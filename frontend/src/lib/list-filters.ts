import type { FilterControl, ListFilter, Model, ModelField } from "@/types";

/**
 * One filter of the list page: a field (or a path across relations,
 * such as "author__country"), or a custom filter with its own options.
 */
export type ResolvedFilter =
  | {
      kind: "field";
      name: string;
      label: string;
      field: ModelField;
      control?: FilterControl;
    }
  | { kind: "custom"; name: string; label: string; multiple: boolean };

/**
 * The model's list filters. Entries are filter descriptions; a plain
 * field name (as older servers sent) uses the model's own field.
 */
export function getListFilters(model: Model): ResolvedFilter[] {
  const entries: (ListFilter | string)[] = model.admin.list.filter ?? [];
  const filters: ResolvedFilter[] = [];

  for (const entry of entries) {
    if (typeof entry === "string") {
      const field = model.fields[entry];
      if (field) {
        filters.push({
          kind: "field",
          name: entry,
          label: field.verbose_name ?? entry,
          field,
        });
      }
    } else if (entry.custom) {
      filters.push({
        kind: "custom",
        name: entry.name,
        label: entry.label,
        multiple: Boolean(entry.multiple),
      });
    } else {
      const field = entry.field ?? model.fields[entry.name];
      if (field) {
        filters.push({
          kind: "field",
          name: entry.name,
          label: entry.label,
          field,
          control: entry.control,
        });
      }
    }
  }

  return filters;
}

/**
 * The filter a query key belongs to: a custom filter by its exact name,
 * a field filter by its path, alone or followed by one "__" lookup
 * ("published__gte"). The longest matching path wins, so "author" and
 * "author__country" can both be filters.
 */
export function matchFilter(
  filters: ResolvedFilter[],
  key: string,
): { filter: ResolvedFilter; lookup: string } | null {
  let match: { filter: ResolvedFilter; lookup: string } | null = null;

  for (const filter of filters) {
    if (filter.kind === "custom") {
      if (key === filter.name) {
        return { filter, lookup: "" };
      }
      continue;
    }

    if (key !== filter.name && !key.startsWith(`${filter.name}__`)) {
      continue;
    }

    const lookup = key.slice(filter.name.length).replace(/^__/, "");

    // A lookup is one word; anything longer belongs to a longer path.
    if (lookup.includes("__")) {
      continue;
    }

    if (!match || filter.name.length > match.filter.name.length) {
      match = { filter, lookup };
    }
  }

  return match;
}

/**
 * A filter's values as one query parameter, comma-joined. A value's own
 * comma is escaped with a backslash, which the server reads back.
 */
export function joinFilterValues(values: string[]): string {
  return values.map((value) => value.replace(/,/g, "\\,")).join(",");
}

/** The values of a comma-joined filter parameter (joinFilterValues). */
export function splitFilterValues(value: string): string[] {
  return value
    .split(/(?<!\\),/)
    .map((part) => part.replace(/\\,/g, ","))
    .filter(Boolean);
}
