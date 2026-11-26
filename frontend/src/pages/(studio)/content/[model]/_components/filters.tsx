import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiPlusBold, PiXBold } from "react-icons/pi";

import { CustomFilter } from "@/components/filters/custom-filter";
import { FilterRenderer } from "@/components/filters/renderer";
import type { FilterChanges, FilterValues } from "@/components/filters/types";
import { Search } from "@/components/search";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

  // Only filters with a value show, as chips. The others wait in the
  // "Filter" menu; the one picked there shows until it has a value,
  // with its options open.
  const [added, setAdded] = useState<string | null>(null);
  const shown = filters.filter(
    (filter) =>
      filter.name === added || Object.keys(valuesOf(filter.name)).length > 0,
  );
  const hidden = filters.filter((filter) => !shown.includes(filter));

  return (
    <div className="flex flex-1 items-center flex-wrap gap-x-1.5 gap-y-2 min-w-0">
      {model.admin.list.search && <Search variant="plain" />}
      {model.admin.list.search && filters.length > 0 && (
        <span
          aria-hidden
          className="hidden sm:block h-5 w-px bg-border mx-1.5"
        />
      )}
      {shown.map((filter) => (
        <span key={filter.name} className="inline-flex items-center min-w-0">
          {filter.kind === "custom" ? (
            <CustomFilter
              name={filter.name}
              label={filter.label}
              multiple={filter.multiple}
              model={model}
              values={valuesOf(filter.name)}
              onChange={(changes) => change(filter.name, changes)}
              defaultOpen={filter.name === added}
            />
          ) : (
            <FilterRenderer
              field={{ ...filter.field, verbose_name: filter.label }}
              control={filter.control}
              name={filter.name}
              model={model}
              values={valuesOf(filter.name)}
              onValueChange={(changes) => change(filter.name, changes)}
              defaultOpen={filter.name === added}
            />
          )}
          {/* A filter picked from the menu shows until it has a value;
              without one, this takes it away again. */}
          {filter.name === added &&
            Object.keys(valuesOf(filter.name)).length === 0 && (
              <Button
                variant="ghost"
                size="icon"
                className="size-6 rounded-full text-muted-foreground"
                aria-label={t("list_view.filters.remove", {
                  field: filter.label,
                })}
                onClick={() => setAdded(null)}
              >
                <PiXBold className="size-3" />
              </Button>
            )}
        </span>
      ))}
      {hidden.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="text-muted-foreground">
              <PiPlusBold />
              {t("list_view.filters.add")}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            // The picked filter opens its own options: focus must not
            // return to this trigger and close them.
            onCloseAutoFocus={(event) => event.preventDefault()}
          >
            {hidden.map((filter) => (
              <DropdownMenuItem
                key={filter.name}
                onSelect={() => setAdded(filter.name)}
              >
                <span className="first-letter:uppercase">{filter.label}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {Object.keys(values).length > 0 && (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => onValuesChange({})}
        >
          {t("list_view.clear_all_filters")}
        </Button>
      )}
    </div>
  );
}
