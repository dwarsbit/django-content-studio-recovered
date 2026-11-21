import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import * as R from "ramda";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiPlusBold } from "react-icons/pi";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { PresenceIndicator } from "@/components/presence";
import { PublishingBadge } from "@/components/publishing/publishing-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import { RelatedObjectDialog } from "@/components/widgets/related-object-dialog";
import { useHttp } from "@/hooks/use-http";
import { usePresenceList } from "@/hooks/use-presence";
import { useRunAction } from "@/hooks/use-run-action";
import {
  arrangeColumns,
  BOARD_PAGE_SIZE,
  type BoardColumnData,
  cardColumn,
  columnKey,
  type MovedCard,
  saveValue,
  showParams,
} from "@/lib/board";
import { cn } from "@/lib/utils";
import type {
  BoardViewConfig,
  BulkAction,
  Model,
  PresenceUser,
  Resource,
} from "@/types";

import { RowMenu } from "./row-menu";

interface BoardResponse {
  columns: BoardColumnData[];
  max_per_column: number;
}

/**
 * The board view: the list's objects as cards in columns, one per value
 * of a choice field or foreign key, with the list's search, filters and
 * ordering. Dragging a card to another column saves its new value at
 * once and offers Undo.
 */
export function BoardView({
  model,
  config,
  params,
  selected,
  onToggle,
  className,
}: {
  model: Model;
  config: BoardViewConfig;
  // The list's search, filters and ordering.
  params: Record<string, string | undefined>;
  // The selected ids, when the model offers bulk actions.
  selected?: Set<string>;
  onToggle?: (id: string) => void;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const http = useHttp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // How many cards each column shows, after "Show more".
  const [shown, setShown] = useState<Record<string, number>>({});
  // Cards shown in the column they were dropped on while they save.
  const [moved, setMoved] = useState<Record<string, MovedCard>>({});
  const [active, setActive] = useState<Resource | null>(null);
  // The column "+" creates an object in.
  const [creating, setCreating] = useState<{
    open: boolean;
    value?: string | number | null;
    label?: string;
  }>({ open: false });
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor),
  );
  const rowActions = model.admin.list.row_actions ?? [];
  const { runAction, dialog } = useRunAction(model);
  const onRunAction = (action: BulkAction, id: string, name?: string) =>
    runAction(action, [id], { name });
  const canAdd = !!model.admin.permissions?.add_permission;

  const { data, isFetching } = useQuery({
    queryKey: ["resources", model.label, "board", config.key, params, shown],
    placeholderData: (previous) => previous,
    async queryFn() {
      const query = new URLSearchParams({ view: config.key });

      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) {
          query.append(key, value);
        }
      }
      for (const [key, value] of showParams(shown)) {
        query.append(key, value);
      }

      const { data } = await http.get<BoardResponse>(
        `/content/${model.label}/board`,
        { params: query },
      );
      return data;
    },
  });

  const columns = arrangeColumns(data?.columns ?? [], moved);
  const items = columns.flatMap((column) => column.results);
  const presence = usePresenceList(
    model,
    items.map((item) => item.id),
  );
  const labelOf = (value: string | number | null, label: string) =>
    value === null
      ? t("list_view.board.none", {
          // In a phrase the field is written lower case, but for German,
          // which capitalizes nouns.
          label: i18n.language.startsWith("de")
            ? config.label
            : config.label.toLocaleLowerCase(),
        })
      : label;
  const columnLabel = (key: string) => {
    const column = columns.find((column) => columnKey(column.value) === key);
    return column ? labelOf(column.value, column.label) : key;
  };
  const valueOf = (key: string) =>
    columns.find((column) => columnKey(column.value) === key)?.value ?? null;

  const draggable = (item: Resource) =>
    config.editable && item.__can_change__ !== false;

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["resources", model.label] });

  // Saves a card's value as a table edit, with the shown value as its
  // base, so someone else's change is not overwritten.
  const save = (item: Resource, to: string, base: unknown) =>
    http.post(`/content/${model.label}/${item.id}/table-edit`, {
      values: { [config.field]: saveValue(config, valueOf(to)) },
      base: { [config.field]: base },
    });

  const move = async (item: Resource, to: string) => {
    const id = String(item.id);
    const from = cardColumn(item, config);

    if (from === to) {
      return;
    }

    setMoved((current) => ({ ...current, [id]: { item, from, to } }));

    try {
      const { data: saved } = await save(item, to, item[config.field]);
      await refresh();
      const savedValue = (saved as { values?: Record<string, unknown> })
        .values?.[config.field];
      toast.success(t("list_view.board.moved", { label: config.label }), {
        description: `${item.__str__} → ${columnLabel(to)}`,
        action: {
          label: t("table_edit.undo"),
          onClick: () => void undo(item, from, to, savedValue),
        },
      });
    } catch (error) {
      toast.error(errorMessage(error, t("table_edit.failed")));
      void refresh();
    } finally {
      setMoved((current) => R.omit([id], current));
    }
  };

  const undo = async (
    item: Resource,
    from: string,
    to: string,
    savedValue: unknown,
  ) => {
    try {
      await save(
        item,
        from,
        savedValue === undefined ? saveValue(config, valueOf(to)) : savedValue,
      );
    } catch (error) {
      toast.error(errorMessage(error, t("table_edit.failed")));
    }
    void refresh();
  };

  const showMore = (key: string, current: number) =>
    setShown((shown) => ({
      ...shown,
      [key]: Math.min(
        current + BOARD_PAGE_SIZE,
        data?.max_per_column ?? current + BOARD_PAGE_SIZE,
      ),
    }));

  return (
    <DndContext
      sensors={sensors}
      autoScroll={false}
      onDragStart={(event) =>
        setActive(items.find((i) => String(i.id) === event.active.id) ?? null)
      }
      onDragCancel={() => setActive(null)}
      onDragEnd={(event) => {
        setActive(null);
        const item = items.find((i) => String(i.id) === event.active.id);

        if (item && event.over) {
          void move(item, String(event.over.id));
        }
      }}
    >
      <div
        className={cn(
          "relative flex gap-3 p-3 w-full items-start overflow-x-auto",
          "snap-x snap-mandatory sm:snap-none",
          className,
        )}
        aria-busy={isFetching}
      >
        {!data && (
          <div className="flex w-full justify-center py-16">
            <Spinner className="size-5 text-muted-foreground" />
          </div>
        )}
        {columns.map((column) => {
          const key = columnKey(column.value);
          const label = labelOf(column.value, column.label);
          const limit = data?.max_per_column ?? 0;

          return (
            <BoardColumn
              key={key}
              id={key}
              label={label}
              count={column.count}
              onAdd={
                canAdd
                  ? () =>
                      setCreating({
                        open: true,
                        value: column.value,
                        label: column.label,
                      })
                  : undefined
              }
              more={
                column.results.length < column.count &&
                column.results.length < limit
                  ? () => showMore(key, column.results.length)
                  : undefined
              }
            >
              {column.results.map((item) => (
                <DraggableCard
                  key={item.id}
                  item={item}
                  model={model}
                  disabled={!draggable(item)}
                  dragging={String(active?.id) === String(item.id)}
                  presence={presence[String(item.id)]}
                  selected={selected?.has(String(item.id))}
                  onToggle={onToggle}
                  rowActions={rowActions}
                  onRunAction={onRunAction}
                  onOpen={() => navigate(`/content/${model.label}/${item.id}`)}
                />
              ))}
            </BoardColumn>
          );
        })}
      </div>
      <DragOverlay dropAnimation={null}>
        {active && (
          <div className="w-64 rotate-2">
            <BoardCard item={active} overlay />
          </div>
        )}
      </DragOverlay>
      {dialog}
      <RelatedObjectDialog
        model={model}
        prefill={
          creating.value === undefined
            ? undefined
            : {
                [config.field]:
                  creating.value === null
                    ? saveValue(config, null)
                    : config.relation
                      ? { id: creating.value, __str__: creating.label }
                      : creating.value,
              }
        }
        readOnly={false}
        open={creating.open}
        onOpenChange={(open) =>
          setCreating((current) => ({ ...current, open }))
        }
        onSaved={async () => {
          setCreating((current) => ({ ...current, open: false }));
          await refresh();
        }}
      />
    </DndContext>
  );
}

function BoardColumn({
  id,
  label,
  count,
  onAdd,
  more,
  children,
}: {
  id: string;
  label: string;
  count: number;
  onAdd?: () => void;
  more?: () => void;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id });

  return (
    <section
      ref={setNodeRef}
      aria-label={label}
      data-column={id}
      className={cn(
        "w-[85%] sm:w-64 shrink-0 snap-start rounded-lg bg-muted/60 flex flex-col transition-colors",
        isOver && "bg-accent ring-2 ring-ring/50",
      )}
    >
      <header className="flex items-center gap-2 px-3 pt-2.5 pb-2 min-h-11">
        <h3 className="text-sm font-semibold truncate">{label}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {count}
        </span>
        {onAdd && (
          <Button
            variant="ghost"
            size="icon-xs"
            className="ml-auto text-muted-foreground"
            aria-label={t("list_view.board.add", { column: label })}
            title={t("list_view.board.add", { column: label })}
            onClick={onAdd}
          >
            <PiPlusBold />
          </Button>
        )}
      </header>
      <div className="flex flex-col gap-2 px-2 pb-2 min-h-24">
        {children}
        {more && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={more}
          >
            {t("list_view.board.show_more")}
          </Button>
        )}
      </div>
    </section>
  );
}

function DraggableCard({
  item,
  model,
  disabled,
  dragging,
  presence,
  selected,
  onToggle,
  rowActions,
  onRunAction,
  onOpen,
}: {
  item: Resource;
  model: Model;
  disabled: boolean;
  dragging: boolean;
  presence?: PresenceUser[];
  selected?: boolean;
  onToggle?: (id: string) => void;
  rowActions: BulkAction[];
  onRunAction(action: BulkAction, id: string, name?: string): void;
  onOpen(): void;
}) {
  const { t } = useTranslation();
  const { setNodeRef, listeners, attributes } = useDraggable({
    id: String(item.id),
    disabled,
  });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      data-card={item.id}
      onClick={onOpen}
      className={cn(
        "group relative rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring",
        dragging && "opacity-30",
      )}
    >
      <BoardCard
        item={item}
        presence={presence}
        locked={disabled}
        selected={selected}
      />
      {(onToggle || rowActions.length > 0) && (
        <div
          className="absolute top-1.5 right-1.5 left-1.5 flex items-center justify-between pointer-events-none"
          onClick={(event) => event.stopPropagation()}
          onPointerDown={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {onToggle ? (
            <span
              className={cn(
                "pointer-events-auto flex rounded-sm bg-card/90 p-0.5 transition-opacity",
                selected
                  ? "opacity-100"
                  : "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
              )}
            >
              <Checkbox
                checked={!!selected}
                aria-label={t("bulk.select_row")}
                onCheckedChange={() => onToggle(String(item.id))}
              />
            </span>
          ) : (
            <span />
          )}
          {rowActions.length > 0 && (
            <span className="pointer-events-auto rounded-md bg-card/90 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
              <RowMenu
                model={model}
                id={String(item.id)}
                name={item.__str__}
                actions={rowActions}
                onRunAction={onRunAction}
              />
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function BoardCard({
  item,
  presence,
  locked,
  selected,
  overlay,
}: {
  item: Resource;
  presence?: PresenceUser[];
  locked?: boolean;
  selected?: boolean;
  overlay?: boolean;
}) {
  const display = item.list_item_display;
  const publishing = item.__publishing__;
  const [failed, setFailed] = useState<string>();

  return (
    <article
      className={cn(
        "rounded-md border bg-card shadow-xs overflow-hidden select-none",
        locked ? "cursor-pointer" : "cursor-grab hover:border-ring/60",
        selected && "border-ring bg-accent",
        overlay && "shadow-xl cursor-grabbing",
      )}
    >
      {display?.thumbnail && failed !== display.thumbnail && (
        <img
          src={display.thumbnail}
          alt=""
          loading="lazy"
          draggable={false}
          onError={() => setFailed(display.thumbnail)}
          className="h-24 w-full object-cover border-b bg-muted"
        />
      )}
      <div className="p-3 flex flex-col gap-1.5">
        <h4 className="text-sm font-medium leading-snug line-clamp-2">
          {display?.title ?? item.__str__}
        </h4>
        {display?.description && (
          <p className="text-xs text-muted-foreground line-clamp-2">
            {display.description}
          </p>
        )}
        {(publishing || display?.meta || (presence && presence.length > 0)) && (
          <div className="flex items-center gap-2 pt-1 min-w-0">
            {publishing ? (
              <PublishingBadge
                state={publishing.state}
                publishedAt={publishing.published_at}
              />
            ) : (
              display?.meta && (
                <Badge variant="outline" className="truncate">
                  {display.meta}
                </Badge>
              )
            )}
            <span className="ml-auto">
              <PresenceIndicator users={presence} />
            </span>
          </div>
        )}
      </div>
    </article>
  );
}

function errorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error) || !error.response) {
    return fallback;
  }

  const data = error.response.data as Record<string, unknown> | undefined;
  const source =
    error.response.status === 409
      ? Object.values((data?.conflicts as Record<string, unknown>) ?? {})
      : Object.values(data ?? {});
  const message = source
    .flatMap((entry) => (Array.isArray(entry) ? entry : [entry]))
    .find((entry) => typeof entry === "string");

  return typeof message === "string" ? message : fallback;
}
