import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Model } from "@/types";

// Widths that change from row to row, so the placeholders read as text.
const WIDTHS = ["w-24", "w-16", "w-20", "w-14", "w-28", "w-12"];
const TITLE_WIDTHS = ["w-64", "w-52", "w-72", "w-44", "w-60", "w-56"];
const cellWidth = (row: number, col: number) =>
  WIDTHS[(row * 3 + col * 5) % WIDTHS.length];
const titleWidth = (row: number) => TITLE_WIDTHS[row % TITLE_WIDTHS.length];

// Enough rows to fill a screen, never more than a page holds.
const rowCount = (model: Model) => Math.min(model.admin.list.per_page, 15);

/**
 * The table while its first page loads: the studio's own columns, with
 * placeholder rows under them.
 */
export function TableSkeleton({ model }: { model: Model }) {
  const { t } = useTranslation();
  const { display, actions, row_actions } = model.admin.list;
  const hasActions = actions.length > 0;
  const hasMenu = (row_actions ?? []).length > 0;

  return (
    <div
      aria-busy
      data-testid="table-skeleton"
      className="w-full flex-1 overflow-hidden"
    >
      <Table>
        <TableHeader>
          <TableRow>
            {hasActions && (
              <TableHead className="bg-muted w-10">
                <span className="block size-4 rounded-[4px] border bg-background" />
              </TableHead>
            )}
            {display.map(({ name, header }) => (
              <TableHead key={name} className="bg-muted">
                <span className="first-letter:uppercase">
                  {header ?? model.fields[name]?.verbose_name ?? name}
                </span>
              </TableHead>
            ))}
            {model.admin.translations && (
              <TableHead className="bg-muted">
                {t("translations.languages_column")}
              </TableHead>
            )}
            {hasMenu && <TableHead className="bg-muted w-10" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: rowCount(model) }, (_, row) => (
            <TableRow key={row} className="hover:bg-transparent">
              {hasActions && (
                <TableCell className="w-10">
                  <Skeleton className="size-4 rounded-[4px]" />
                </TableCell>
              )}
              {display.map(({ name }, col) => (
                <TableCell key={name}>
                  <div className="min-h-8 flex items-center">
                    <Skeleton
                      className={cn(
                        "h-3.5",
                        col === 0 ? titleWidth(row) : cellWidth(row, col),
                      )}
                    />
                  </div>
                </TableCell>
              ))}
              {model.admin.translations && (
                <TableCell>
                  <Skeleton className="h-5 w-24" />
                </TableCell>
              )}
              {hasMenu && <TableCell className="w-10" />}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** The list view while it loads: a picture, a title and a line per row. */
export function ListRowsSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <ul aria-busy data-testid="list-skeleton" className="divide-y">
      {Array.from({ length: rows }, (_, row) => (
        <li key={row} className="px-4 py-3 flex items-center gap-3">
          <Skeleton className="size-10 rounded-md shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className={cn("h-3.5", titleWidth(row))} />
            <Skeleton className={cn("h-3", cellWidth(row, 2))} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** The gallery while it loads: tiles with a caption. */
export function GallerySkeleton({
  size = "large",
  tiles = 10,
}: {
  size?: "large" | "small";
  tiles?: number;
}) {
  return (
    <ul
      aria-busy
      data-testid="gallery-skeleton"
      className={cn(
        "grid w-full",
        size === "large"
          ? "grid-cols-2 gap-4 p-4 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]"
          : "grid-cols-2 gap-3 p-3 sm:grid-cols-[repeat(auto-fill,minmax(150px,1fr))]",
      )}
    >
      {Array.from({ length: tiles }, (_, i) => (
        <li key={i} className="flex flex-col gap-2">
          <Skeleton className="aspect-[4/3] rounded-lg" />
          <Skeleton className={cn("h-3.5", i % 2 ? "w-1/2" : "w-3/4")} />
        </li>
      ))}
    </ul>
  );
}

/** The trash while it loads: a name, a date and the buttons per row. */
export function TrashSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div aria-busy data-testid="trash-skeleton" className="border divide-y">
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="px-4 py-2 flex items-center gap-6">
          <div className="flex-1 min-w-0 h-8 flex items-center">
            <Skeleton className={cn("h-3.5", titleWidth(row))} />
          </div>
          <Skeleton className="h-3.5 w-36" />
          <Skeleton className="h-7 w-36 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

/** The media library while it loads, in the view it shows. */
export function MediaSkeleton({
  view,
  items = 12,
}: {
  // The library's view: "grid", "list" or "table".
  view: string;
  items?: number;
}) {
  if (view === "grid") {
    return (
      <div
        aria-busy
        data-testid="media-skeleton"
        className="grid grid-cols-[repeat(auto-fill,minmax(168px,1fr))] gap-4"
      >
        {Array.from({ length: items }, (_, i) => (
          <div key={i} className="rounded-lg border bg-card overflow-hidden">
            <Skeleton className="aspect-[4/3] rounded-none" />
            <div className="px-3 py-2 space-y-2">
              <Skeleton className={cn("h-3.5", i % 2 ? "w-1/2" : "w-3/4")} />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      aria-busy
      data-testid="media-skeleton"
      className="rounded-lg border bg-card divide-y"
    >
      {Array.from({ length: items }, (_, row) => (
        <div key={row} className="px-4 py-2 flex items-center gap-3">
          <Skeleton
            className={cn(
              "rounded-md shrink-0",
              view === "list" ? "size-10" : "size-7",
            )}
          />
          <div className="flex-1 space-y-2">
            <Skeleton className={cn("h-3.5", titleWidth(row))} />
            {view === "list" && (
              <Skeleton className={cn("h-3", cellWidth(row, 2))} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
