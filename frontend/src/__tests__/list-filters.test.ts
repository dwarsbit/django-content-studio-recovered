import { describe, expect, it } from "vitest";

import { matchFilter, type ResolvedFilter } from "@/lib/list-filters";
import { FieldType } from "@/types";

const field = { type: FieldType.CharField };

const filters: ResolvedFilter[] = [
  { kind: "field", name: "author", label: "Author", field },
  { kind: "field", name: "author__country", label: "Author country", field },
  { kind: "custom", name: "popularity", label: "Popularity", multiple: false },
];

describe("matchFilter", () => {
  it("matches a path alone or with one lookup", () => {
    expect(matchFilter(filters, "author")?.filter.name).toBe("author");
    expect(matchFilter(filters, "author__in")).toMatchObject({
      filter: { name: "author" },
      lookup: "in",
    });
  });

  it("prefers the longest path", () => {
    expect(matchFilter(filters, "author__country")).toMatchObject({
      filter: { name: "author__country" },
      lookup: "",
    });
    expect(matchFilter(filters, "author__country__in")).toMatchObject({
      filter: { name: "author__country" },
      lookup: "in",
    });
  });

  it("matches custom filters by their exact name", () => {
    expect(matchFilter(filters, "popularity")?.filter.kind).toBe("custom");
    expect(matchFilter(filters, "popularity__gte")).toBeNull();
  });

  it("rejects keys past a path", () => {
    expect(matchFilter(filters, "author__email")).toMatchObject({
      filter: { name: "author" },
      lookup: "email",
    });
    expect(matchFilter(filters, "author__email__startswith")).toBeNull();
    expect(matchFilter(filters, "title")).toBeNull();
  });
});
