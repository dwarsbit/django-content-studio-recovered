import * as R from "ramda";
import { useTranslation } from "react-i18next";
import { TbCaretDownFilled, TbCaretUpFilled } from "react-icons/tb";
import { useNavigate } from "react-router";

import { FormatRenderer } from "@/components/formats/renderer";
import { PresenceIndicator } from "@/components/presence";
import { Reorderable, RowDragHandle } from "@/components/reorderable";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useReorderableRow } from "@/hooks/use-reorderable-row";
import { useRunAction } from "@/hooks/use-run-action";
import { useContentLanguage } from "@/lib/content-language";
import { getEdges, type Move } from "@/lib/reorder";
import { cn } from "@/lib/utils";
import {
  type BulkAction,
  FieldType,
  type Id,
  type Model,
  type PresenceUser,
} from "@/types";

import { ListEmptyState } from "./empty-state";
import { RowMenu } from "./row-menu";

type Row = { id: string; __str__?: string; [p: string]: unknown };

// Numbers line up on the right, in tabular figures.
const NUMERIC_TYPES: FieldType[] = [
  FieldType.IntegerField,
  FieldType.DecimalField,
  FieldType.FloatField,
];

function isNumeric(type: FieldType | undefined) {
  return type !== undefined && NUMERIC_TYPES.includes(type);
}

// Reordering, when the list offers it: the moves a drop or the row
// menu make, why reordering is off right now (null when it is on), and
// whether the page is the list's first or last, where rows cannot move
// further up or down.
export interface ReorderProps {
  disabledReason: string | null;
  onMove(id: Id, move: Move): void;
  isFirstPage: boolean;
  isLastPage: boolean;
}

export function TableView({
  items,
  model,
  selected,
  ordering,
  onOrderingChange,
  onToggle,
  onToggleAll,
  filtered,
  onClear,
  reorder,
  presence,
  className,
}: {
  items: Row[];
  model: Model;
  // The selected ids, when the model offers bulk actions.
  selected?: Set<string>;
  // The remembered ordering: a field name, prefixed with "-" for
  // descending, or null for the default ordering.
  ordering?: string | null;
  onOrderingChange?: (next: string | null) => void;
  onToggle?: (id: string) => void;
  onToggleAll?: (ids: string[]) => void;
  // Whether a search term or remembered filters narrow the list;
  // drives the empty state's no-results notice.
  filtered?: boolean;
  // Clears the search term and the remembered filters.
  onClear?: () => void;
  reorder?: ReorderProps;
  // The other users who have objects open, by id.
  presence?: Record<string, PresenceUser[]>;
  // Overrides the frame: the list card drops the view's own border.
  className?: string;
}) {
  const { t } = useTranslation();
  const fields = model.admin.list.display;
  const { sortable_by, display } = model.admin.list;
  const hasActions = (model.admin.list.actions ?? []).length > 0;
  const rowActions = model.admin.list.row_actions ?? [];
  // The last column holds each row's menu: its row actions, and the
  // moves when the list can be reordered.
  const hasMenu = !!reorder || rowActions.length > 0;
  const { runAction, dialog } = useRunAction(model);
  const onRunAction = (action: BulkAction, id: string, name?: string) =>
    runAction(action, [id], { name });
  const allSelected =
    hasActions &&
    items.length > 0 &&
    items.every((item) => selected?.has(item.id));

  return (
    <div
      className={cn(
        "w-full flex-1 scrollbar overflow-auto border rounded-lg",
        className,
      )}
    >
      <Table>
        <TableHeader>
          <TableRow>
            {reorder && (
              <TableHead className="sticky top-0 z-10 bg-muted w-8">
                <span className="sr-only">{t("reorder.drag")}</span>
              </TableHead>
            )}
            {hasActions && (
              <TableHead className="sticky top-0 z-10 bg-muted w-10">
                <Checkbox
                  checked={allSelected}
                  aria-label={t("bulk.select_all")}
                  onCheckedChange={() =>
                    onToggleAll?.(items.map((item) => item.id))
                  }
                />
              </TableHead>
            )}
            {display.map(({ name, header }) => {
              const label = header ?? model.fields[name]?.verbose_name;
              const numeric = isNumeric(model.fields[name]?.type);
              const active = name === ordering?.replace(/^-/, "");
              const descending = !!ordering?.startsWith("-");
              // Computed columns have no queryset equivalent to sort on.
              const isSortable =
                !R.isNil(model.fields[name]) &&
                (R.isNil(sortable_by) || sortable_by.includes(name));

              return (
                <TableHead
                  key={name}
                  aria-sort={
                    isSortable
                      ? active
                        ? descending
                          ? "descending"
                          : "ascending"
                        : "none"
                      : undefined
                  }
                  className={cn("sticky top-0 z-10 bg-muted", {
                    "[&_div]:justify-end": numeric,
                  })}
                >
                  {label && isSortable ? (
                    <button
                      onClick={() => {
                        if (!active) {
                          onOrderingChange?.(name);
                        } else if (descending) {
                          onOrderingChange?.(null);
                        } else {
                          onOrderingChange?.(`-${name}`);
                        }
                      }}
                      className={cn(
                        "group inline-flex items-center gap-1 cursor-pointer rounded-sm hover:text-foreground",
                        "outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        { "text-foreground": active },
                      )}
                    >
                      <span className="first-letter:uppercase">{label}</span>
                      <span
                        className={cn({
                          invisible: !active,
                        })}
                      >
                        {descending ? (
                          <TbCaretUpFilled />
                        ) : (
                          <TbCaretDownFilled />
                        )}
                      </span>
                    </button>
                  ) : (
                    label
                  )}
                </TableHead>
              );
            })}
            {model.admin.translations && (
              <TableHead className="sticky top-0 z-10 bg-muted">
                {t("translations.languages_column")}
              </TableHead>
            )}
            {hasMenu && (
              <TableHead className="sticky top-0 z-10 bg-muted w-10">
                <span className="sr-only">{t("row_actions.menu")}</span>
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {R.isEmpty(items) && (
            <TableRow>
              <TableCell
                colSpan={
                  fields.length +
                  (hasActions ? 1 : 0) +
                  (reorder ? 1 : 0) +
                  (hasMenu ? 1 : 0)
                }
                className="text-center"
              >
                <ListEmptyState
                  model={model}
                  filtered={!!filtered}
                  onClear={onClear}
                />
              </TableCell>
            </TableRow>
          )}
          {reorder ? (
            <Reorderable
              ids={items.map((item) => item.id)}
              getLabel={(id) =>
                items.find((item) => String(item.id) === String(id))?.__str__ ??
                id
              }
              onMove={reorder.onMove}
            >
              {items.map((item, index) => (
                <SortableTableViewRow
                  key={item.id}
                  item={item}
                  edges={getEdges(index, items.length, reorder)}
                  model={model}
                  hasActions={hasActions}
                  selected={!!selected?.has(item.id)}
                  onToggle={onToggle}
                  reorder={reorder}
                  rowActions={rowActions}
                  onRunAction={onRunAction}
                  presence={presence?.[String(item.id)]}
                />
              ))}
            </Reorderable>
          ) : (
            items.map((item) => (
              <TableViewRow
                key={item.id}
                item={item}
                model={model}
                hasActions={hasActions}
                selected={!!selected?.has(item.id)}
                onToggle={onToggle}
                rowActions={rowActions}
                onRunAction={onRunAction}
                presence={presence?.[String(item.id)]}
              />
            ))
          )}
        </TableBody>
      </Table>
      {dialog}
    </div>
  );
}

function SortableTableViewRow(
  props: Omit<Parameters<typeof TableViewRow>[0], "sortable"> & {
    reorder: ReorderProps;
  },
) {
  const sortable = useReorderableRow(
    props.item.id,
    !!props.reorder.disabledReason,
  );

  return <TableViewRow {...props} sortable={sortable} />;
}

function TableViewRow({
  item,
  model,
  hasActions,
  selected,
  onToggle,
  reorder,
  sortable,
  edges,
  presence,
  rowActions,
  onRunAction,
}: {
  item: Row;
  model: Model;
  hasActions: boolean;
  selected: boolean;
  onToggle?: (id: string) => void;
  reorder?: ReorderProps;
  rowActions: BulkAction[];
  onRunAction(action: BulkAction, id: string, name?: string): void;
  presence?: PresenceUser[];
  sortable?: ReturnType<typeof useReorderableRow>;
  edges?: ReturnType<typeof getEdges>;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fields = model.admin.list.display;
  const { config: translations, language } = useContentLanguage();
  const languageStates = item.__languages__ as
    Record<string, number> | undefined;

  return (
    <TableRow
      ref={sortable?.ref}
      style={sortable?.style}
      data-state={selected ? "selected" : undefined}
      onClick={() => navigate(`/content/${model.label}/${item.id}`)}
      className={cn({ "bg-muted shadow-sm": sortable?.isDragging })}
    >
      {reorder && sortable && (
        <TableCell className="w-8 pr-0">
          <RowDragHandle
            handleProps={sortable.handleProps}
            disabledReason={reorder.disabledReason}
          />
        </TableCell>
      )}
      {hasActions && (
        <TableCell
          className="w-10"
          onClick={(event) => event.stopPropagation()}
        >
          <Checkbox
            checked={selected}
            aria-label={t("bulk.select_row")}
            onCheckedChange={() => onToggle?.(item.id)}
          />
        </TableCell>
      )}
      {fields.map(({ name, format }, index) => (
        <TableCell
          key={name}
          className={cn({
            "font-medium": index === 0,
            "text-right tabular-nums": isNumeric(model.fields[name]?.type),
          })}
        >
          <div
            className={cn("truncate min-h-8 items-center flex", {
              "justify-end": isNumeric(model.fields[name]?.type),
            })}
          >
            <TranslatedCell
              item={item}
              name={name}
              column={translations?.fields[name]?.[language]}
              defaultLanguage={translations?.default}
            >
              {(value) => (
                <FormatRenderer
                  value={value}
                  field={model.fields[name]}
                  format={format}
                />
              )}
            </TranslatedCell>
            {index === 0 && (
              <PresenceIndicator users={presence} className="ml-2" />
            )}
          </div>
        </TableCell>
      ))}
      {translations && (
        <TableCell>
          <LanguageBadges
            languages={translations.languages.map((l) => l.code)}
            states={languageStates}
          />
        </TableCell>
      )}
      {(reorder || rowActions.length > 0) && (
        <TableCell
          className="w-10"
          onClick={(event) => event.stopPropagation()}
        >
          <RowMenu
            model={model}
            id={item.id}
            name={item.__str__}
            actions={rowActions}
            onRunAction={onRunAction}
            move={
              reorder && {
                disabledReason: reorder.disabledReason,
                onMove: (move) => reorder.onMove(item.id, move),
                ...edges,
              }
            }
          />
        </TableCell>
      )}
    </TableRow>
  );
}

function TranslatedCell({
  item,
  name,
  column,
  defaultLanguage,
  children,
}: {
  item: Record<string, unknown>;
  name: string;
  column?: string;
  defaultLanguage?: string;
  children: (value: unknown) => React.ReactNode;
}) {
  if (!column || column === name) {
    return children(item[name]);
  }

  const value = item[column];

  if (value === "" || value == null) {
    // Not translated: the default language's value, muted.
    return (
      <span className="flex items-center gap-1.5 min-w-0 text-muted-foreground font-normal">
        <span className="shrink-0 rounded bg-muted px-1 py-px text-[10px] font-semibold uppercase tracking-wide">
          {defaultLanguage}
        </span>
        <span className="truncate italic">{children(item[name])}</span>
      </span>
    );
  }

  return children(value);
}

function LanguageBadges({
  languages,
  states,
}: {
  languages: string[];
  states?: Record<string, number>;
}) {
  return (
    <div className="flex items-center gap-1">
      {languages.map((code) => {
        const missing = states?.[code] ?? 0;

        return (
          <span
            key={code}
            className={cn(
              "inline-flex items-center h-5 px-1.5 rounded border text-[10px] font-semibold uppercase tracking-wide",
              missing === 0
                ? "bg-background text-foreground"
                : "border-dashed text-muted-foreground/60",
            )}
          >
            {code}
          </span>
        );
      })}
    </div>
  );
}
