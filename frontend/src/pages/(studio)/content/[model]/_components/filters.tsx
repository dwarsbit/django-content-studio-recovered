import { useTranslation } from "react-i18next";

import { CustomFilter } from "@/components/filters/custom-filter";
import { FilterRenderer } from "@/components/filters/renderer";
import type { FilterChanges, FilterValues } from "@/components/filters/types";
import { Search } from "@/components/search";
import { Button } from "@/components/ui/button";
import { getListFilters, matchFilter } from "@/lib/list-filters";
import type { Model } from "@/types";

/**
 * Collects the remembered values of one filter field, keyed by lookup
 * suffix ("", "gte", ...). Exact matches take the field name; a `__`
 * suffix carries the lookup, so "published__gte" becomes "gte".
 */
function getFilterValues(
  values: Record<string, string>,
  name: string,
): FilterValues {
  const collected: FilterValues = {};

  for (const [key, value] of Object.entries(values)) {
    if (key !== name && !key.startsWith(`${name}__`)) {
      continue;
    }
    collected[key.slice(name.length).replace(/^__/, "")] = value;
  }

  return collected;
}

export function Filters({
  model,
  values,
  onValuesChange,
}: {
  model: Model;
  // The remembered filter values: "field" / "field__lookup" to value.
  values: Record<string, string>;
  onValuesChange: (next: Record<string, string>) => void;
}) {
  const { t } = useTranslation();
  const filters = getListFilters(model);
  // A field and a longer path across it ("author", "author__country")
  // must not share values: each key belongs to the longest path.
  const valuesOf = (name: string) =>
    getFilterValues(
      Object.fromEntries(
        Object.entries(values).filter(
          ([key]) => matchFilter(filters, key)?.filter.name === name,
        ),
      ),
      name,
    );

  const change = (name: string, changes: FilterChanges) => {
    const next = { ...values };

    for (const [lookup, value] of Object.entries(changes)) {
      const key = `${name}${lookup ? `__${lookup}` : ""}`;
      if (value) {
        next[key] = value;
      } else {
        delete next[key];
      }
    }

    onValuesChange(next);
  };

  return (
    <div className="flex items-start flex-wrap gap-x-4 gap-y-2 min-w-0">
      {model.admin.list.search && <Search />}
      {filters.map((filter) =>
        filter.kind === "custom" ? (
          <CustomFilter
            key={filter.name}
            name={filter.name}
            label={filter.label}
            multiple={filter.multiple}
            model={model}
            values={valuesOf(filter.name)}
            onChange={(changes) => change(filter.name, changes)}
          />
        ) : (
          <FilterRenderer
            key={filter.name}
            field={{ ...filter.field, verbose_name: filter.label }}
            name={filter.name}
            model={model}
            values={valuesOf(filter.name)}
            onValueChange={(changes) => change(filter.name, changes)}
          />
        ),
      )}
      {Object.keys(values).length > 0 && (
        <Button variant="ghost" onClick={() => onValuesChange({})}>
          {t("list_view.clear_all_filters")}
        </Button>
      )}
    </div>
  );
}
