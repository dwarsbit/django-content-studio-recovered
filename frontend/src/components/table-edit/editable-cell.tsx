import { keepPreviousData, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import * as R from "ramda";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiCaretDownBold,
  PiCheckBold,
  PiWarningCircleBold,
} from "react-icons/pi";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RelationOption } from "@/components/widgets/relation-option";
import { TimeWidget } from "@/components/widgets/time-widget";
import { useHttp } from "@/hooks/use-http";
import { getCellKind } from "@/lib/table-edit";
import { cn } from "@/lib/utils";
import { FieldType, type Model, type ModelField, type Resource } from "@/types";

const NUMERIC: FieldType[] = [
  FieldType.IntegerField,
  FieldType.DecimalField,
  FieldType.FloatField,
];

/**
 * Moves the focus to the next (or previous) editable cell of the table,
 * opening it when it is a text cell: Tab walks the table like a sheet.
 */
function focusNextCell(from: Element | null, backwards: boolean) {
  const cells = Array.from(
    document.querySelectorAll<HTMLElement>("[data-table-edit-cell]"),
  );
  const current = from?.closest("[data-table-edit-cell]");
  const index = current ? cells.indexOf(current as HTMLElement) : -1;
  const next = cells[index + (backwards ? -1 : 1)];

  if (!next) {
    return;
  }

  // After the current cell has re-rendered out of its input.
  window.setTimeout(() => {
    const target =
      next.querySelector<HTMLElement>("[data-cell-control]") ?? next;

    target.focus();

    if (next.dataset.kind === "text") {
      target.click();
    }
  });
}

/**
 * A table cell edited in place (table_edit): a switch for booleans, a
 * select for choices, a picker for foreign keys and dates, an input for
 * the rest. It saves as soon as it is left: a spinner while it saves, a
 * check once saved, and on an error a red ring with the reason in a
 * tooltip, keeping the typed value (Esc puts the saved one back).
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
  // Shown in an empty cell: a missing translation's default language.
  placeholder?: string;
  onChange(value: unknown): void;
  onRevert(): void;
  // The value as the column formats it.
  children: ReactNode;
}) {
  const field = model.fields[name];
  const kind = getCellKind(field);
  const numeric = NUMERIC.includes(field?.type as FieldType);
  const frame = cn(
    "relative -mx-2 px-2 min-h-8 w-[calc(100%+1rem)] flex items-center gap-2 rounded-md transition-colors outline-none",
    "ring-inset hover:ring-1 hover:ring-input hover:bg-background focus-visible:ring-2 focus-visible:ring-ring",
    {
      "justify-end": numeric,
      "bg-success/10": saved && !error,
      "bg-destructive/8 ring-1 ring-destructive/70 hover:bg-destructive/10 hover:ring-destructive":
        !!error,
    },
  );
  const marker = (
    <CellMarker
      saving={saving}
      saved={saved}
      error={error}
      className={numeric ? "order-first mr-auto" : "ml-auto"}
    />
  );
  const cell = {
    "data-table-edit-cell": "",
    "data-kind": kind,
    onClick: (event: React.MouseEvent) => event.stopPropagation(),
  };
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape" && error) {
      onRevert();
    }
  };

  if (kind === "boolean") {
    return (
      <div {...cell} className={cn(frame, "w-auto cursor-default")}>
        <Switch
          data-cell-control
          checked={Boolean(value)}
          onCheckedChange={onChange}
          aria-label={field?.verbose_name}
          onKeyDown={(event) => {
            if (event.key === "Tab") {
              event.preventDefault();
              focusNextCell(event.currentTarget, event.shiftKey);
            }
          }}
        />
        {marker}
      </div>
    );
  }

  if (kind === "choice" && field) {
    return (
      <div {...cell} className="contents">
        <ChoiceCell
          field={field}
          value={value}
          onChange={onChange}
          className={frame}
          onKeyDown={onKeyDown}
        >
          <span className="truncate">{children}</span>
          {marker}
        </ChoiceCell>
      </div>
    );
  }

  if (kind === "relation") {
    return (
      <div {...cell} className="contents">
        <RelationCell
          model={model}
          name={name}
          field={field}
          value={value as Resource | null}
          onChange={onChange}
          className={frame}
          onKeyDown={onKeyDown}
        >
          <span className="truncate">{children}</span>
          {marker}
        </RelationCell>
      </div>
    );
  }

  if ((kind === "date" || kind === "datetime") && field) {
    return (
      <div {...cell} className="contents">
        <DateCell
          field={field}
          withTime={kind === "datetime"}
          value={value as string | null}
          onChange={onChange}
          className={frame}
          onKeyDown={onKeyDown}
        >
          <span className="truncate">{children}</span>
          {marker}
        </DateCell>
      </div>
    );
  }

  return (
    <div {...cell} className="contents">
      <TextCell
        value={value}
        numeric={numeric}
        placeholder={placeholder}
        label={field?.verbose_name}
        onChange={onChange}
        onRevert={error ? onRevert : undefined}
        className={frame}
        marker={marker}
      >
        {children}
      </TextCell>
    </div>
  );
}

function CellMarker({
  saving,
  saved,
  error,
  className,
}: {
  saving: boolean;
  saved: boolean;
  error?: string[];
  className?: string;
}) {
  const { t } = useTranslation();

  if (saving) {
    return (
      <span
        role="status"
        aria-label={t("table_edit.saving")}
        className={cn("shrink-0 text-muted-foreground", className)}
      >
        <Spinner className="size-3.5" />
      </span>
    );
  }

  if (error) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            role="img"
            aria-label={error.join(" ")}
            className={cn("shrink-0 text-destructive", className)}
          >
            <PiWarningCircleBold />
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-64">
          {error.join(" ")}
        </TooltipContent>
      </Tooltip>
    );
  }

  if (saved) {
    return (
      <span
        role="status"
        aria-label={t("table_edit.saved_short")}
        className={cn("shrink-0 text-success", className)}
      >
        <PiCheckBold />
      </span>
    );
  }

  return null;
}

function TextCell({
  value,
  numeric,
  placeholder,
  label,
  onChange,
  onRevert,
  className,
  marker,
  children,
}: {
  value: unknown;
  numeric: boolean;
  placeholder?: string;
  label?: string;
  onChange(value: unknown): void;
  onRevert?(): void;
  className: string;
  marker: ReactNode;
  children: ReactNode;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const open = () => setDraft(R.isNil(value) ? "" : String(value));
  const commit = () => {
    if (draft === null) {
      return;
    }

    // An emptied number is null; the server says whether it may be.
    onChange(numeric ? (draft.trim() === "" ? null : draft.trim()) : draft);
    setDraft(null);
  };

  if (draft !== null) {
    return (
      <div
        className={cn(
          className,
          "p-0 bg-background ring-2 ring-ring hover:ring-2 hover:ring-ring",
        )}
      >
        <Input
          autoFocus
          aria-label={label}
          value={draft}
          placeholder={placeholder}
          inputMode={numeric ? "decimal" : undefined}
          onFocus={(event) => event.target.select()}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              setDraft(null);
              onRevert?.();
            } else if (event.key === "Tab") {
              event.preventDefault();
              commit();
              focusNextCell(event.currentTarget, event.shiftKey);
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
      data-cell-control
      aria-label={label}
      className={cn(className, "cursor-text")}
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === "F2") {
          event.preventDefault();
          open();
        } else if (event.key === "Escape") {
          onRevert?.();
        }
      }}
    >
      {empty && placeholder ? (
        <span className="truncate italic text-muted-foreground font-normal">
          {placeholder}
        </span>
      ) : (
        <span className="truncate">{children}</span>
      )}
      {marker}
    </div>
  );
}

function ChoiceCell({
  field,
  value,
  onChange,
  className,
  onKeyDown,
  children,
}: {
  field: ModelField;
  value: unknown;
  onChange(value: unknown): void;
  className: string;
  onKeyDown(event: React.KeyboardEvent): void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  // Choice values arrive typed (a number for an IntegerField); the
  // select works with strings.
  const choices = field.choices ?? [];

  return (
    <Select
      value={R.isNil(value) ? "" : String(value)}
      onValueChange={(next) =>
        onChange(
          next === "__clear__"
            ? null
            : ((choices.find(([v]) => String(v) === next)?.[0] as unknown) ??
                next),
        )
      }
    >
      <SelectTrigger
        data-cell-control
        size="sm"
        aria-label={field.verbose_name}
        onKeyDown={onKeyDown}
        className={cn(
          className,
          "group/cell h-auto border-0 shadow-none bg-transparent dark:bg-transparent px-2 [&>svg:last-child]:opacity-0 hover:[&>svg:last-child]:opacity-50 data-[state=open]:[&>svg:last-child]:opacity-50",
        )}
      >
        {children}
      </SelectTrigger>
      <SelectContent>
        {choices.map(([choice, label]) => (
          <SelectItem key={String(choice)} value={String(choice)}>
            {label}
          </SelectItem>
        ))}
        {!field.required && !R.isNil(value) && value !== "" && (
          <>
            <SelectSeparator />
            <SelectItem value="__clear__">{t("common.clear")}</SelectItem>
          </>
        )}
      </SelectContent>
    </Select>
  );
}

function RelationCell({
  model,
  name,
  field,
  value,
  onChange,
  className,
  onKeyDown,
  children,
}: {
  model: Model;
  name: string;
  field?: ModelField;
  value: Resource | null;
  onChange(value: unknown): void;
  className: string;
  onKeyDown(event: React.KeyboardEvent): void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { data = [], isLoading } = useQuery({
    enabled: open,
    queryKey: ["related-model", model.label, name, "table-edit", search],
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
        data-cell-control
        aria-label={field?.verbose_name}
        onKeyDown={onKeyDown}
        className={cn(className, "group/rel cursor-pointer text-left")}
      >
        {children}
        <PiCaretDownBold
          className={cn(
            "size-3.5 shrink-0 opacity-0 group-hover/rel:opacity-50",
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
            ) : R.isEmpty(data) ? (
              <div className="py-6 text-center text-sm text-muted-foreground select-none">
                {t("widgets.relation_widget.no_results")}
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
          {!field?.required && value && (
            <div className="p-2 border-t">
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                {t("common.clear")}
              </Button>
            </div>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function DateCell({
  field,
  withTime,
  value,
  onChange,
  className,
  onKeyDown,
  children,
}: {
  field: ModelField;
  withTime: boolean;
  value: string | null;
  onChange(value: unknown): void;
  className: string;
  onKeyDown(event: React.KeyboardEvent): void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const current = value ? dayjs(value) : null;
  const [date, setDate] = useState<Date | undefined>();
  const [time, setTime] = useState("00:00");

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setDate(current?.toDate());
      setTime(current?.format("HH:mm") ?? "00:00");
    } else if (withTime && date) {
      // A date and time saves when the picker closes.
      const picked = dayjs(`${dayjs(date).format("YYYY-MM-DD")}T${time}`);

      if (picked.isValid() && !current?.isSame(picked, "minute")) {
        onChange(picked.format());
      }
    }

    setOpen(next);
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger
        data-cell-control
        aria-label={field.verbose_name}
        onKeyDown={onKeyDown}
        className={cn(className, "group/date cursor-pointer text-left")}
      >
        {children}
        <PiCaretDownBold
          className={cn(
            "size-3.5 shrink-0 opacity-0 group-hover/date:opacity-50",
            open && "opacity-50",
          )}
        />
      </PopoverTrigger>
      <PopoverContent
        className="w-auto overflow-hidden p-0"
        align="start"
        onClick={(event) => event.stopPropagation()}
      >
        <Calendar
          mode="single"
          fixedWeeks
          defaultMonth={current?.toDate()}
          selected={withTime ? date : current?.toDate()}
          onSelect={(picked) => {
            if (!picked) {
              return;
            }

            if (withTime) {
              setDate(picked);
            } else {
              onChange(dayjs(picked).format("YYYY-MM-DD"));
              setOpen(false);
            }
          }}
        />
        {withTime && (
          <div className="p-3 border-t">
            <TimeWidget value={time} onChange={setTime} />
          </div>
        )}
        {!field.required && value && (
          <div className="p-3 border-t">
            <Button
              variant="outline"
              className="w-full"
              size="sm"
              onClick={() => {
                onChange(null);
                setDate(undefined);
                setOpen(false);
              }}
            >
              {t("common.clear")}
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
