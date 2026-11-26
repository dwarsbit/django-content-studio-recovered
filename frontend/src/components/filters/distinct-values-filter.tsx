import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiCheckBold } from "react-icons/pi";

import {
  Command,
  CommandGroup,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Spinner } from "@/components/ui/spinner";
import { useHttp } from "@/hooks/use-http";
import { joinFilterValues, splitFilterValues } from "@/lib/list-filters";

import { FilterTrigger } from "./filter-trigger";
import type { FilterComponentProps } from "./types";

interface DistinctValues {
  values: string[];
  // More values exist than the server sent: search finds them.
  more: boolean;
}

/**
 * A text field without choices: a searchable multi-select over the
 * values in the table, like the classic admin's AllValuesFieldListFilter.
 * The server sends the first 100, narrowed by the search; picking
 * several matches any of them.
 */
export function DistinctValuesFilter({
  field,
  model,
  name,
  values,
  onChange,
  defaultOpen,
}: FilterComponentProps) {
  const { t } = useTranslation();
  const http = useHttp();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(!!defaultOpen);
  const selected = splitFilterValues(values[""] ?? "");

  const { data, isLoading } = useQuery({
    enabled: open,
    queryKey: ["filter-values", model.label, name, search],
    placeholderData: keepPreviousData,
    async queryFn() {
      const { data } = await http.get<DistinctValues>(
        `/content/${model.label}/filters/${name}/values`,
        { params: { search: search || undefined } },
      );

      return data;
    },
  });

  const options = data?.values ?? [];

  const toggle = (value: string) => {
    const next = selected.includes(value)
      ? selected.filter((current) => current !== value)
      : [...selected, value];

    onChange({ "": joinFilterValues(next) || null });
  };

  return (
    <Popover modal open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <FilterTrigger
          label={field.verbose_name}
          value={selected.join(", ")}
          onClear={() => onChange({ "": null })}
        />
      </PopoverTrigger>
      <PopoverContent
        className="max-h-[400px] w-80 max-w-[calc(100vw-2rem)] overflow-hidden p-0 flex flex-col"
        align="start"
      >
        <div className="border-b border-border">
          <Input
            autoFocus
            placeholder={t("common.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border-0"
          />
        </div>
        <Command shouldFilter={false}>
          <CommandList className="scrollbar">
            {isLoading ? (
              <div role="status" className="py-6 flex justify-center">
                <Spinner />
              </div>
            ) : options.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground select-none">
                {t("widgets.relation_widget.no_results")}
              </div>
            ) : (
              <CommandGroup>
                {options.map((option) => (
                  <CommandItem
                    key={option}
                    value={option}
                    onSelect={() => toggle(option)}
                  >
                    <span className="flex-1 flex items-start gap-2 min-w-0">
                      {selected.includes(option) ? (
                        <PiCheckBold className="size-4 shrink-0 mt-0.5" />
                      ) : (
                        <span className="size-4 shrink-0 mt-0.5" />
                      )}
                      <span className="min-w-0 break-words">{option}</span>
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
        {data?.more && (
          <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground select-none">
            {t("list_view.filters.more_values")}
          </div>
        )}
        {selected.length > 0 && (
          <div className="border-t border-border p-2">
            <button
              type="button"
              className="w-full text-sm text-muted-foreground hover:text-foreground rounded-sm py-1 cursor-pointer"
              onClick={() => onChange({ "": null })}
            >
              {t("common.clear")}
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
