import * as R from "ramda";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { joinFilterValues, splitFilterValues } from "@/lib/list-filters";

import { FilterTrigger } from "./filter-trigger";
import type { FilterComponentProps } from "./types";

export function MultiSelectFilter({
  field,
  values,
  onChange,
  defaultOpen,
}: FilterComponentProps) {
  const valueArray = splitFilterValues(values[""] ?? "");
  const choices = R.fromPairs(field.choices ?? []);

  return (
    <DropdownMenu defaultOpen={defaultOpen}>
      <DropdownMenuTrigger asChild>
        <FilterTrigger
          label={field.verbose_name}
          value={valueArray
            .filter(Boolean)
            .map((value) => choices[value])
            .join(", ")}
          onClear={() => onChange({ "": null })}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        {field.choices?.map(([choice, label]) => {
          // The query string holds text; choices of an integer field
          // are numbers.
          const key = String(choice);

          return (
            <DropdownMenuCheckboxItem
              key={key}
              checked={valueArray.includes(key)}
              onSelect={(e) => {
                e.preventDefault();
                onChange({
                  "":
                    joinFilterValues(
                      valueArray.includes(key)
                        ? valueArray.filter((i) => i !== key)
                        : [...valueArray, key],
                    ) || null,
                });
              }}
            >
              {label}
            </DropdownMenuCheckboxItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
