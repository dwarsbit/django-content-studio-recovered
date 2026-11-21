import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiImage } from "react-icons/pi";
import { useNavigate } from "react-router";

import { PresenceIndicator } from "@/components/presence";
import { PublishingBadge } from "@/components/publishing/publishing-badge";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { useRunAction } from "@/hooks/use-run-action";
import { cn } from "@/lib/utils";
import type { BulkAction, Model, PresenceUser, Resource } from "@/types";

import { ListEmptyState } from "./empty-state";
import { RowMenu } from "./row-menu";

export type GallerySize = "small" | "large";

/**
 * The gallery view: the list's page as image tiles, from the
 * thumbnail, title and meta of the list item display. Tiles open the
 * editor; the selection checkbox and the row menu show on hover, like
 * the media library grid.
 */
export function GalleryView({
  items,
  model,
  size = "large",
  selected,
  onToggle,
  filtered,
  onClear,
  presence,
  className,
}: {
  items: Resource[];
  model: Model;
  size?: GallerySize;
  // The selected ids, when the model offers bulk actions.
  selected?: Set<string>;
  onToggle?: (id: string) => void;
  filtered?: boolean;
  onClear?: () => void;
  presence?: Record<string, PresenceUser[]>;
  className?: string;
}) {
  const rowActions = model.admin.list.row_actions ?? [];
  const { runAction, dialog } = useRunAction(model);
  const onRunAction = (action: BulkAction, id: string, name?: string) =>
    runAction(action, [id], { name });

  return (
    <div className={cn("w-full", className)}>
      {items.length === 0 ? (
        <ListEmptyState model={model} filtered={!!filtered} onClear={onClear} />
      ) : (
        <ul
          data-size={size}
          className={cn(
            "grid w-full",
            size === "large"
              ? "grid-cols-2 gap-4 p-4 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]"
              : "grid-cols-2 gap-3 p-3 sm:grid-cols-[repeat(auto-fill,minmax(150px,1fr))]",
          )}
        >
          {items.map((item) => (
            <GalleryTile
              key={item.id}
              item={item}
              model={model}
              size={size}
              selected={selected?.has(String(item.id))}
              onToggle={onToggle}
              presence={presence?.[String(item.id)]}
              rowActions={rowActions}
              onRunAction={onRunAction}
            />
          ))}
        </ul>
      )}
      {dialog}
    </div>
  );
}

function GalleryTile({
  item,
  model,
  size,
  selected,
  onToggle,
  presence,
  rowActions,
  onRunAction,
}: {
  item: Resource;
  model: Model;
  size: GallerySize;
  selected?: boolean;
  onToggle?: (id: string) => void;
  presence?: PresenceUser[];
  rowActions: BulkAction[];
  onRunAction(action: BulkAction, id: string, name?: string): void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const display = item.list_item_display;
  const publishing = item.__publishing__;
  const title = display?.title ?? item.__str__;
  // The source that failed to load, so a changed source is tried again.
  const [failed, setFailed] = useState<string>();
  const src = display?.thumbnail;

  return (
    <li
      data-tile={item.id}
      onClick={() => navigate(`/content/${model.label}/${item.id}`)}
      className="group flex flex-col gap-2 min-w-0 cursor-pointer select-none"
    >
      <div
        className={cn(
          "relative aspect-[4/3] rounded-lg overflow-hidden border bg-muted",
          "transition-shadow group-hover:ring-2 group-hover:ring-ring/40",
          selected && "ring-2 ring-primary group-hover:ring-primary",
        )}
      >
        {src && failed !== src ? (
          <img
            src={src}
            alt=""
            loading="lazy"
            draggable={false}
            onError={() => setFailed(src)}
            className="size-full object-cover"
          />
        ) : (
          <span
            data-testid="gallery-placeholder"
            className="size-full flex items-center justify-center text-muted-foreground"
          >
            <PiImage className={size === "large" ? "size-8" : "size-6"} />
          </span>
        )}
        {onToggle && (
          <span
            className={cn(
              "absolute top-2 left-2 flex rounded-sm bg-background/90 p-0.5 transition-opacity",
              selected
                ? "opacity-100"
                : "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
            )}
            onClick={(event) => event.stopPropagation()}
          >
            <Checkbox
              checked={!!selected}
              aria-label={t("bulk.select_row")}
              onCheckedChange={() => onToggle(String(item.id))}
            />
          </span>
        )}
        {rowActions.length > 0 && (
          <span
            className="absolute top-1.5 right-1.5 rounded-md bg-background/90 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity"
            onClick={(event) => event.stopPropagation()}
          >
            <RowMenu
              model={model}
              id={String(item.id)}
              name={item.__str__}
              actions={rowActions}
              onRunAction={onRunAction}
            />
          </span>
        )}
        {publishing?.state && publishing.state !== "published" && (
          // An opaque backing keeps the tinted badge legible on any image.
          <span className="absolute bottom-2 left-2 max-w-[calc(100%-1rem)] rounded-md bg-background shadow-sm">
            <PublishingBadge
              state={publishing.state}
              publishedAt={publishing.published_at}
              short={size === "small"}
              className="max-w-full truncate"
            />
          </span>
        )}
        {presence && presence.length > 0 && (
          <span className="absolute bottom-2 right-2">
            <PresenceIndicator users={presence} />
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1 px-0.5 min-w-0">
        <h3
          className={cn(
            "font-medium leading-snug line-clamp-2",
            size === "large" ? "text-sm" : "text-xs",
          )}
          title={title}
        >
          {title}
        </h3>
        {size === "large" && display?.meta && !publishing && (
          <Badge variant="outline" className="self-start max-w-full truncate">
            {display.meta}
          </Badge>
        )}
      </div>
    </li>
  );
}
