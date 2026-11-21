import { keepPreviousData, useQuery } from "@tanstack/react-query";
import * as R from "ramda";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { FiChevronDown } from "react-icons/fi";
import { PiCheckBold, PiWarningCircleBold } from "react-icons/pi";

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
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RelationOption } from "@/components/widgets/relation-option";
import { useHttp } from "@/hooks/use-http";
import { cn } from "@/lib/utils";
import { FieldType, FieldWidget, type Model, type Resource } from "@/types";

const NUMERIC: FieldType[] = [
  FieldType.IntegerField,
  FieldType.DecimalField,
  FieldType.FloatField,
];

/**
 * A table cell edited in place (WIP prototype of list_edit): a switch
 * for booleans, a relation picker for foreign keys and an input for
 * the rest. A cell saves as soon as it is left: a spinner while it
 * saves, a check once saved, and on an error a red ring with the reason
 * in a tooltip, keeping the typed value (Esc puts the saved one back).
 */
export function EditableCell({
  model,
  name,
  value,
  saving,
  saved,
  error,
  placeholder,
  onChange,
  onRevert,
  children,
}: {
  model: Model;
  name: string;
  value: unknown;
  saving: boolean;
  saved: boolean;
  error?: string[];
  placeholder?: string;
  onChange(value: unknown): void;
  onRevert(): void;
  children: ReactNode;
}) {
  const field = model.fields[name];
  const numeric = NUMERIC.includes(field?.type as FieldType);
  const frame = cn(
    "relative -mx-2 px-2 min-h-8 w-[calc(100%+1rem)] flex items-center rounded-md transition-colors",
    "ring-inset hover:ring-1 hover:ring-input hover:bg-background",
    {
      "justify-end": numeric,
      "bg-success/10 transition-colors duration-700": saved && !error,
      "bg-destructive/8 ring-1 ring-destructive/70 hover:bg-destructive/10 hover:ring-destructive":
        !!error,
    },
  );
  const side = numeric ? "mr-auto pr-2" : "ml-auto pl-2";
  const marker = saving ? (
    <span className={cn("shrink-0 text-muted-foreground", side)}>
      <Spinner className="size-3.5" />
    </span>
  ) : saved && !error ? (
    <span className={cn("shrink-0 text-success", side)}>
      <PiCheckBold />
    </span>
  ) : error ? (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "text-destructive shrink-0",
            numeric ? "mr-auto" : "ml-auto pl-2",
          )}
        >
          <PiWarningCircleBold />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-64">
        {error.join(" ")}
      </TooltipContent>
    </Tooltip>
  ) : null;

  if (field?.type === FieldType.BooleanField) {
    return (
      <div
        className={cn(frame, "w-auto cursor-default")}
        onClick={(event) => event.stopPropagation()}
      >
        <Switch
          checked={Boolean(value)}
          onCheckedChange={onChange}
          aria-label={field.verbose_name}
        />
        {marker}
      </div>
    );
  }

  if (
    field?.widget_class === FieldWidget.ForeignKeyWidget ||
    (field?.type as string) === "ForeignKey"
  ) {
    return (
      <RelationCell
        model={model}
        name={name}
        value={value as Resource | null}
        onChange={onChange}
        className={frame}
        marker={marker}
      >
        {children}
      </RelationCell>
    );
  }

  return (
    <TextCell
      value={value}
      numeric={numeric}
      placeholder={placeholder}
      onChange={onChange}
      onRevert={error ? onRevert : undefined}
      className={frame}
      marker={marker}
      label={field?.verbose_name}
    >
      {children}
    </TextCell>
  );
}

function TextCell({
  value,
  numeric,
  placeholder,
  onChange,
  onRevert,
  className,
  marker,
  label,
  children,
}: {
  value: unknown;
  numeric: boolean;
  placeholder?: string;
  onChange(value: unknown): void;
  onRevert?(): void;
  className: string;
  marker: ReactNode;
  label?: string;
  children: ReactNode;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft === null) {
      return;
    }

    onChange(numeric && draft !== "" ? Number(draft) : draft);
    setDraft(null);
  };

  if (draft !== null) {
    return (
      <div
        className={cn(
          className,
          "ring-2 ring-ring bg-background p-0 hover:ring-2 hover:ring-ring",
        )}
      >
        <Input
          autoFocus
          aria-label={label}
          value={draft}
          placeholder={placeholder}
          inputMode={numeric ? "numeric" : undefined}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              commit();
            } else if (event.key === "Escape") {
              setDraft(null);
              onRevert?.();
            }
          }}
          className={cn(
            "h-8 border-0 bg-transparent px-2 font-[inherit]",
            numeric && "text-right tabular-nums",
          )}
        />
      </div>
    );
  }

  const empty = value === "" || R.isNil(value);

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(className, "cursor-text")}
      onClick={(event) => {
        event.stopPropagation();
        setDraft(R.isNil(value) ? "" : String(value));
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          setDraft(R.isNil(value) ? "" : String(value));
        } else if (event.key === "Escape") {
          onRevert?.();
        }
      }}
    >
      {numeric && marker}
      {empty && placeholder ? (
        <span className="truncate italic text-muted-foreground font-normal">
          {placeholder}
        </span>
      ) : (
        <span className="truncate">{children}</span>
      )}
      {!numeric && marker}
    </div>
  );
}

function RelationCell({
  model,
  name,
  value,
  onChange,
  className,
  marker,
  children,
}: {
  model: Model;
  name: string;
  value: Resource | null;
  onChange(value: unknown): void;
  className: string;
  marker: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { data = [], isLoading } = useQuery({
    enabled: open,
    queryKey: ["related-model", model.label, name, "list-edit", search],
    placeholderData: keepPreviousData,
    async queryFn() {
      const { data } = await http.post<Resource[]>(
        `/content/${model.label}/relations/${name}`,
        { search, form: {} },
      );

      return data;
    },
  });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className={cn(className, "group/rel cursor-pointer text-left")}
        onClick={(event) => event.stopPropagation()}
      >
        <span className="truncate flex-1 min-w-0">{children}</span>
        {marker}
        <FiChevronDown
          className={cn(
            "size-4 shrink-0 ml-1 opacity-0 group-hover/rel:opacity-50",
            open && "opacity-50",
          )}
        />
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-64 max-h-80 overflow-hidden p-0 flex flex-col"
        onClick={(event) => event.stopPropagation()}
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
            ) : (
              <CommandGroup>
                {data.map((option) => (
                  <CommandItem
                    key={option.id}
                    data-checked={String(option.id) === String(value?.id)}
                    className="data-[checked=true]:bg-accent"
                    onSelect={() => {
                      onChange(option);
                      setOpen(false);
                    }}
                  >
                    <RelationOption option={option} />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
