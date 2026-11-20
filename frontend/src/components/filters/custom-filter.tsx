import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Spinner } from "@/components/ui/spinner";
import { useHttp } from "@/hooks/use-http";
import type { Model } from "@/types";

import { FilterTrigger } from "./filter-trigger";
import type { FilterChanges, FilterValues } from "./types";

interface FilterOption {
  value: string;
  label: string;
}

/**
 * A custom filter of the studio (a ListFilter class): a dropdown of the
 * options the server builds for this request. They are fetched when the
 * dropdown opens, or while a value needs its label. Single choice
 * filters pick one option, multiple choice filters any number, sent as
 * a comma-joined list.
 */
export function CustomFilter({
  name,
  label,
  multiple,
  model,
  values,
  onChange,
  defaultOpen,
}: {
  name: string;
  label: string;
  multiple: boolean;
  model: Model;
  values: FilterValues;
  onChange(changes: FilterChanges): void;
  defaultOpen?: boolean;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const [open, setOpen] = useState(!!defaultOpen);
  const value = values[""] ?? "";
  const selected = value.split(",").filter(Boolean);

  const { data: options = [], isLoading } = useQuery({
    enabled: open || selected.length > 0,
    queryKey: ["filter-options", model.label, name],
    async queryFn() {
      const { data } = await http.get<FilterOption[]>(
        `/content/${model.label}/filters/${name}/options`,
      );

      return data;
    },
  });

  const labels = Object.fromEntries(options.map((o) => [o.value, o.label]));

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <FilterTrigger
          label={label}
          value={selected.map((v) => labels[v] ?? v).join(", ")}
          onClear={() => onChange({ "": null })}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {isLoading ? (
          <div role="status" className="py-4 px-8 flex justify-center">
            <Spinner />
          </div>
        ) : options.length === 0 ? (
          <div className="py-4 px-3 text-sm text-muted-foreground select-none">
            {t("widgets.relation_widget.no_results")}
          </div>
        ) : multiple ? (
          options.map((option) => (
            <DropdownMenuCheckboxItem
              key={option.value}
              checked={selected.includes(option.value)}
              onSelect={(e) => {
                e.preventDefault();
                const next = selected.includes(option.value)
                  ? selected.filter((v) => v !== option.value)
                  : [...selected, option.value];

                onChange({ "": next.join(",") || null });
              }}
            >
              {option.label}
            </DropdownMenuCheckboxItem>
          ))
        ) : (
          <DropdownMenuRadioGroup
            value={value}
            onValueChange={(next) =>
              onChange({ "": next === value ? null : next })
            }
          >
            <DropdownMenuRadioItem value="">
              {t("list_view.filters.all")}
            </DropdownMenuRadioItem>
            {options.map((option) => (
              <DropdownMenuRadioItem key={option.value} value={option.value}>
                {option.label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
