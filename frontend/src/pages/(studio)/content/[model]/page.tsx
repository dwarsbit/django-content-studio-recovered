import { keepPreviousData, useQuery } from "@tanstack/react-query";
import * as R from "ramda";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiCalendarBlankBold,
  PiFileTextBold,
  PiGridNineBold,
  PiImagesSquareBold,
  PiKanbanBold,
  PiRowsBold,
  PiSquaresFourBold,
  PiTableBold,
} from "react-icons/pi";
import { Link, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import {
  ContentLanguageProvider,
  LanguageMenu,
} from "@/components/content-editor/content-language";
import { HeaderTabs } from "@/components/header-tabs";
import { ImportDialog } from "@/components/import-dialog";
import { buttonVariants } from "@/components/ui/button";
import { PageBody, PageHeader } from "@/components/ui/page-header";
import { ListPagination } from "@/components/ui/pagination";
import { Spinner } from "@/components/ui/spinner";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useDiscover } from "@/hooks/use-discover";
import { useExport } from "@/hooks/use-export";
import { useHttp } from "@/hooks/use-http";
import { useImportDownload } from "@/hooks/use-import";
import { useMoveResource } from "@/hooks/use-move-resource";
import { usePresenceList } from "@/hooks/use-presence";
import { useTableEdit } from "@/hooks/use-table-edit";
import { getDownloadErrorMessage } from "@/lib/download";
import { formatNumber } from "@/lib/format-number";
import { getListFilters, matchFilter } from "@/lib/list-filters";
import { isCounted } from "@/lib/list-pagination";
import { safeStorage } from "@/lib/safe-storage";
import type {
  ExportFormat,
  ImportFormat,
  ListResponse,
  Model,
  PaginatedResponse,
  Resource,
} from "@/types";

import { BoardView } from "./_components/board-view";
import { ContentBulkBar } from "./_components/bulk-bar";
import { CalendarView } from "./_components/calendar-view";
import { Filters } from "./_components/filters";
import { type GallerySize, GalleryView } from "./_components/gallery-view";
import { ListActionsMenu } from "./_components/list-actions-menu";
import { ListView } from "./_components/list-view";
import { SortSelect } from "./_components/sort-select";
import { type ReorderProps, TableView } from "./_components/table-view";
import { findBoard, findCalendar, viewKey } from "./_components/view-config";
import { ContentEditorPage } from "./[id]/page";

export function ModelListPage() {
  const { t, i18n } = useTranslation();
  const { model: appLabel } = useParams<{ model: string }>();
  const http = useHttp();
  const { data: discover } = useDiscover();
  const model = discover?.models.find(R.whereEq({ label: appLabel }));
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Number(searchParams.get("page") ?? "1");
  const search = searchParams.get("search");
  // The views the admin offers; more than one shows a toggle. The
  // choice is remembered per content type in local storage.
  const viewConfigs = model?.admin.list.views ?? ["table"];
  const views = viewConfigs.map(viewKey);
  const sortableBy = model?.admin.list.sortable_by ?? null;

  // Reads the remembered choice, falling back to the first offered
  // view when nothing (or a no longer offered view) is stored.
  const storedView = (label: string) => {
    const remembered = safeStorage.get(`__dcs_list_view__:${label}`);

    return remembered && views.includes(remembered) ? remembered : views[0];
  };

  // The remembered ordering (null meaning none) and filters (a flat
  // record of "field" / "field__lookup" to value), per content type.
  // A remembered value can outlive the studio's configuration — a
  // removed column, filter or sortable field is dropped instead of
  // being sent as an ignored parameter.
  const sanitizeOrdering = (ordering: string | null) => {
    const name = ordering?.replace(/^-/, "");

    return ordering &&
      name &&
      model &&
      !R.isNil(model.fields[name]) &&
      model.admin.list.display.some((column) => column.name === name) &&
      (R.isNil(sortableBy) || sortableBy.includes(name))
      ? ordering
      : null;
  };
  const sanitizeFilters = (filters: Record<string, string>) => {
    if (!model) {
      return {};
    }

    const listFilters = getListFilters(model);

    return Object.fromEntries(
      Object.entries(filters).filter(([key]) =>
        Boolean(matchFilter(listFilters, key)),
      ),
    );
  };
  const storedOrdering = (label: string) =>
    sanitizeOrdering(safeStorage.get(`__dcs_list_ordering__:${label}`));
  const storedFilters = (label: string) => {
    try {
      return sanitizeFilters(
        JSON.parse(
          safeStorage.get(`__dcs_list_filters__:${label}`) ?? "{}",
        ) as Record<string, string>,
      );
    } catch {
      return {};
    }
  };

  const [view, setViewState] = useState<string>(() =>
    model?.label ? storedView(model.label) : views[0],
  );
  // The calendar or board the view switch shows, if it shows one.
  const calendar = findCalendar(viewConfigs, view);
  const board = findBoard(viewConfigs, view);
  // The gallery's tile size, remembered per content type.
  const [gallerySize, setGallerySizeState] = useState<GallerySize>(() =>
    model?.label &&
    safeStorage.get(`__dcs_gallery_size__:${model.label}`) === "small"
      ? "small"
      : "large",
  );
  const setGallerySize = (next: GallerySize) => {
    setGallerySizeState(next);

    if (model) {
      safeStorage.set(`__dcs_gallery_size__:${model.label}`, next);
    }
  };
  const [ordering, setOrderingState] = useState<string | null>(() =>
    model?.label ? storedOrdering(model.label) : null,
  );
  const [filters, setFiltersState] = useState<Record<string, string>>(() =>
    model?.label ? storedFilters(model.label) : {},
  );
  const [lastLabel, setLastLabel] = useState(model?.label);

  // Navigating between content types re-reads the remembered choice,
  // ordering and filters.
  if (model && model.label !== lastLabel) {
    setLastLabel(model.label);
    setViewState(storedView(model.label));
    setGallerySizeState(
      safeStorage.get(`__dcs_gallery_size__:${model.label}`) === "small"
        ? "small"
        : "large",
    );
    setOrderingState(storedOrdering(model.label));
    setFiltersState(storedFilters(model.label));
  }

  // Without sortable_by the list view always uses the default
  // ordering; the stored ordering is kept for the table to pick
  // back up.
  const effectiveOrdering =
    (view === "list" || view === "gallery" || board) && R.isNil(sortableBy)
      ? null
      : ordering;

  // Selection is current-page: any URL change (page, search) or
  // change of the remembered ordering or filters resets it — during
  // render, the sanctioned way to adjust state to an external change.
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [lastParams, setLastParams] = useState(searchParams);

  if (searchParams !== lastParams) {
    setLastParams(searchParams);
    setSelected(new Set());
  }

  const setView = (next: string) => {
    setViewState(next);

    if (model) {
      safeStorage.set(`__dcs_list_view__:${model.label}`, next);
    }

    // Selection is current-page: switching views resets it.
    setSelected(new Set());
  };

  // Narrowing or re-sorting the list can strand the current page, so
  // every state change returns to the first page.
  const resetPage = () =>
    setSearchParams((searchParams) => {
      searchParams.delete("page");
      return searchParams;
    });

  const setOrdering = (next: string | null) => {
    setOrderingState(next);

    if (model) {
      if (next) {
        safeStorage.set(`__dcs_list_ordering__:${model.label}`, next);
      } else {
        safeStorage.remove(`__dcs_list_ordering__:${model.label}`);
      }
    }

    resetPage();
    setSelected(new Set());
  };

  const setFilters = (next: Record<string, string>) => {
    setFiltersState(next);

    if (model) {
      if (R.isEmpty(next)) {
        safeStorage.remove(`__dcs_list_filters__:${model.label}`);
      } else {
        safeStorage.set(
          `__dcs_list_filters__:${model.label}`,
          JSON.stringify(next),
        );
      }
    }

    resetPage();
    setSelected(new Set());
  };

  const toggle = (id: string) =>
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });

  const toggleAll = (ids: string[]) =>
    setSelected((previous) =>
      ids.every((id) => previous.has(id)) ? new Set() : new Set(ids),
    );

  // Whether a search term or remembered filters narrow the list —
  // the empty state's no-results notice depends on it — and clearing
  // both.
  const filtered = !R.isEmpty(filters) || !!search;
  const clearContext = () => {
    setFilters({});
    setSearchParams((searchParams) => {
      searchParams.delete("search");
      return searchParams;
    });
  };

  const clearSelection = () => setSelected(new Set());
  const actions = model?.admin.list.actions ?? [];

  // Export writes every object matching the search and filters, in the
  // list's ordering: all pages, not only the current one.
  const exportFormats = model?.admin.list.export?.formats ?? [];
  const { mutateAsync: runExport, isPending: isExporting } = useExport(
    appLabel ?? "",
  );
  const exportList = async (format: ExportFormat) => {
    try {
      await runExport({
        format,
        params: {
          ...filters,
          search: search || undefined,
          ordering: effectiveOrdering,
        },
      });
    } catch (e) {
      toast.error(await getDownloadErrorMessage(e));
    }
  };

  // Import: the dialog, and the list "For import" in the export menu.
  const importConfig = model?.admin.list.import ?? null;
  const [importOpen, setImportOpen] = useState(false);
  const { mutateAsync: runImportExport, isPending: isImportExporting } =
    useImportDownload(appLabel ?? "");
  const exportForImport = async (format: ImportFormat) => {
    try {
      await runImportExport({
        format,
        params: {
          ...filters,
          search: search || undefined,
          ordering: effectiveOrdering,
        },
      });
    } catch (e) {
      toast.error(await getDownloadErrorMessage(e));
    }
  };

  const queryKey = [
    "resources",
    appLabel,
    { search, page, ordering: effectiveOrdering, filters },
  ];

  const { data } = useQuery({
    retry: false,
    enabled: !R.isNil(model),
    queryKey,
    placeholderData: keepPreviousData,
    async queryFn() {
      const { data } = await http.get<ListResponse<Resource>>(
        `/content/${appLabel}`,
        {
          params: {
            ...filters,
            search: search || undefined,
            page,
            ordering: effectiveOrdering,
          },
        },
      );

      return data;
    },
  });

  // Inline editing of the table (table_edit): each cell saves when left.
  const edit = useTableEdit(model);

  // Who else has the objects of this page open.
  const presence = usePresenceList(
    model,
    (data?.results ?? []).map((item) => item.id),
  );

  // Reordering follows the manual order, so it is off while another
  // ordering or a search (ranked results) decides the order; filters
  // only narrow the list and keep it on.
  const { mutate: move } = useMoveResource({
    endpoint: `/content/${appLabel}`,
    queryKey,
    invalidateKey: ["resources", appLabel],
    params: filters,
  });
  const reorder: ReorderProps | undefined = model?.admin.list.reorderable
    ? {
        disabledReason: search
          ? t("reorder.disabled_search")
          : effectiveOrdering
            ? t("reorder.disabled_ordering")
            : null,
        onMove: (id, next) => move({ id, move: next }),
        isFirstPage: !data || data.pagination.current <= 1,
        isLastPage: !data || !data.pagination.has_next,
      }
    : undefined;

  return model && data ? (
    <ContentLanguageProvider model={model}>
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
        <PageHeader
          icon={
            model.admin.icon ? (
              <span className={model.admin.icon} />
            ) : (
              <PiFileTextBold />
            )
          }
          title={model.verbose_name_plural}
          description={model.admin.list.description}
          actions={
            <>
              <ListActionsMenu
                exportFormats={exportFormats}
                onExport={exportList}
                importFormats={importConfig?.formats}
                onExportForImport={importConfig ? exportForImport : undefined}
                onImport={
                  importConfig?.can_import
                    ? () => setImportOpen(true)
                    : undefined
                }
                disabled={isExporting || isImportExporting}
              />
              {model.admin.permissions.add_permission && (
                <Link
                  to={`/content/${model.label}/new`}
                  className={buttonVariants()}
                >
                  {t("common.create")}
                </Link>
              )}
            </>
          }
        >
          {model.admin.list.trash && <ListTabs model={model} current="list" />}
        </PageHeader>
        {importConfig?.can_import && (
          <ImportDialog
            model={model}
            open={importOpen}
            onOpenChange={setImportOpen}
          />
        )}

        <PageBody className="space-y-3">
          {/* One card: the toolbar (search, filters, sorting, the view
            toggle) sits on the list it controls. */}
          <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
            <div className="min-h-12 p-2 flex items-start gap-2 border-b">
              <Filters
                key={model.label}
                model={model}
                values={filters}
                onValuesChange={setFilters}
              />
              {/* Scrolls sideways when a phone cannot fit every toggle. */}
              <div className="ml-auto h-8 min-w-0 flex items-center gap-1 overflow-x-auto">
                {model.admin.translations && (
                  <>
                    <LanguageMenu className="h-8" />
                    <span aria-hidden className="h-5 w-px bg-border mx-1" />
                  </>
                )}
                {data.pagination.count !== null && (
                  <span
                    className="mr-2 text-muted-foreground text-sm tabular-nums select-none"
                    title={
                      data.pagination.approximate
                        ? t("list_view.count_about", {
                            total: formatNumber(data.pagination.count, {
                              format: "full",
                              locale: i18n.language,
                            }),
                            plural: model.verbose_name_plural,
                          })
                        : undefined
                    }
                  >
                    {data.pagination.approximate
                      ? `~${formatNumber(data.pagination.count, { locale: i18n.language })}`
                      : formatNumber(data.pagination.count, {
                          format: "full",
                          locale: i18n.language,
                        })}
                  </span>
                )}
                {view === "gallery" && (
                  <ToggleGroup
                    type="single"
                    size="sm"
                    value={gallerySize}
                    onValueChange={(next) =>
                      next && setGallerySize(next as GallerySize)
                    }
                    aria-label={t("list_view.gallery.size")}
                    // A phone shows two columns of either size.
                    className="hidden sm:flex gap-0.5 mr-1"
                  >
                    <ToggleGroupItem
                      value="large"
                      title={t("list_view.gallery.large")}
                      aria-label={t("list_view.gallery.large")}
                      className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                    >
                      <PiSquaresFourBold />
                    </ToggleGroupItem>
                    <ToggleGroupItem
                      value="small"
                      title={t("list_view.gallery.small")}
                      aria-label={t("list_view.gallery.small")}
                      className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                    >
                      <PiGridNineBold />
                    </ToggleGroupItem>
                  </ToggleGroup>
                )}
                {(view === "list" || view === "gallery" || board) &&
                  !R.isNil(sortableBy) && (
                    <SortSelect
                      model={model}
                      ordering={ordering}
                      onOrderingChange={setOrdering}
                    />
                  )}
                {views.length > 1 && (
                  <>
                    <span aria-hidden className="h-5 w-px bg-border mx-1" />
                    <ToggleGroup
                      type="single"
                      size="sm"
                      value={view}
                      onValueChange={(next) => next && setView(next)}
                      aria-label={t("list_view.view")}
                      className="gap-0.5"
                    >
                      {views.includes("table") && (
                        <ToggleGroupItem
                          value="table"
                          title={t("list_view.table_view")}
                          aria-label={t("list_view.table_view")}
                          className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                        >
                          <PiTableBold />
                        </ToggleGroupItem>
                      )}
                      {views.includes("list") && (
                        <ToggleGroupItem
                          value="list"
                          title={t("list_view.list_view")}
                          aria-label={t("list_view.list_view")}
                          className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                        >
                          <PiRowsBold />
                        </ToggleGroupItem>
                      )}
                      {views.includes("gallery") && (
                        <ToggleGroupItem
                          value="gallery"
                          title={t("list_view.gallery_view")}
                          aria-label={t("list_view.gallery_view")}
                          className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                        >
                          <PiImagesSquareBold />
                        </ToggleGroupItem>
                      )}
                      {viewConfigs.map(
                        (config) =>
                          typeof config !== "string" &&
                          config.type === "calendar" && (
                            <ToggleGroupItem
                              key={config.key}
                              value={config.key}
                              title={t("list_view.calendar_view", {
                                label: config.label,
                              })}
                              aria-label={t("list_view.calendar_view", {
                                label: config.label,
                              })}
                              className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                            >
                              <PiCalendarBlankBold />
                            </ToggleGroupItem>
                          ),
                      )}
                      {viewConfigs.map(
                        (config) =>
                          typeof config !== "string" &&
                          config.type === "board" && (
                            <ToggleGroupItem
                              key={config.key}
                              value={config.key}
                              title={t("list_view.board_view", {
                                label: config.label,
                              })}
                              aria-label={t("list_view.board_view", {
                                label: config.label,
                              })}
                              className="min-w-8 rounded-md first:rounded-md last:rounded-md text-muted-foreground"
                            >
                              <PiKanbanBold />
                            </ToggleGroupItem>
                          ),
                      )}
                    </ToggleGroup>
                  </>
                )}
              </div>
            </div>
            {calendar ? (
              <CalendarView
                key={calendar.key}
                model={model}
                config={calendar}
                params={{ ...filters, search: search || undefined }}
              />
            ) : board ? (
              <BoardView
                key={board.key}
                model={model}
                config={board}
                params={{
                  ...filters,
                  search: search || undefined,
                  ordering: effectiveOrdering ?? undefined,
                }}
                selected={actions.length > 0 ? selected : undefined}
                onToggle={actions.length > 0 ? toggle : undefined}
              />
            ) : view === "gallery" ? (
              <GalleryView
                items={data.results}
                model={model}
                size={gallerySize}
                selected={actions.length > 0 ? selected : undefined}
                onToggle={actions.length > 0 ? toggle : undefined}
                filtered={filtered}
                onClear={clearContext}
                presence={presence}
              />
            ) : view === "list" ? (
              <ListView
                items={data.results}
                model={model}
                selected={actions.length > 0 ? selected : undefined}
                onToggle={actions.length > 0 ? toggle : undefined}
                filtered={filtered}
                onClear={clearContext}
                reorder={reorder}
                presence={presence}
                className="border-0 rounded-none"
              />
            ) : (
              <TableView
                items={data.results}
                model={model}
                selected={selected}
                ordering={ordering}
                onOrderingChange={setOrdering}
                onToggle={toggle}
                onToggleAll={toggleAll}
                filtered={filtered}
                onClear={clearContext}
                reorder={reorder}
                presence={presence}
                edit={edit.editable.length > 0 ? edit : undefined}
                className="border-0 rounded-none"
              />
            )}
          </div>
          {data.results.length > 0 && !calendar && !board && (
            <div className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
              <span className="tabular-nums select-none">
                <ListCount model={model} pagination={data.pagination} />
              </span>
              <ListPagination
                pagination={data.pagination}
                onPageChange={(page) =>
                  setSearchParams((searchParams) => {
                    searchParams.set("page", `${page}`);
                    return searchParams;
                  })
                }
              />
            </div>
          )}
        </PageBody>

        {selected.size > 0 && actions.length > 0 && (
          <ContentBulkBar
            model={model}
            actions={actions}
            ids={Array.from(selected)}
            ordering={effectiveOrdering}
            onDone={clearSelection}
          />
        )}
      </div>
    </ContentLanguageProvider>
  ) : (
    <div className="flex-1 flex items-center justify-center">
      <Spinner />
    </div>
  );
}

/**
 * The list's count and page: "120 articles · Page 2 of 6" when counted,
 * "About 2.3M articles · Page 2" with an estimate and "Page 2" when the
 * list is not counted.
 */
function ListCount({
  model,
  pagination,
}: {
  model: Model;
  pagination: ListResponse<Resource>["pagination"];
}) {
  const { t, i18n } = useTranslation();

  if (isCounted(pagination)) {
    return (
      <>
        {t("list_view.count", {
          count: pagination.count,
          singular: model.verbose_name,
          plural: model.verbose_name_plural,
        })}
        {pagination.pages > 1 &&
          ` · ${t("list_view.page_of", { current: pagination.current, pages: pagination.pages })}`}
      </>
    );
  }

  const page = t("list_view.page", { current: pagination.current });

  return pagination.count !== null
    ? `${t("list_view.count_about", {
        total: formatNumber(pagination.count, { locale: i18n.language }),
        plural: model.verbose_name_plural,
      })} · ${page}`
    : page;
}

/**
 * The scope tabs of a model with a trash: the list and the trash, with
 * the number of objects in the trash.
 */
export function ListTabs({
  model,
  current,
  count,
}: {
  model: Model;
  current: "list" | "trash";
  // The number of objects in the trash, when the caller has it; the
  // list page fetches it.
  count?: number;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const { data: fetched } = useQuery({
    retry: false,
    enabled: count === undefined,
    queryKey: ["trash", model.label, "count"],
    async queryFn() {
      const { data } = await http.get<PaginatedResponse<Resource>>(
        `/content/${model.label}/trash`,
        { params: { page: 1 } },
      );

      return data.pagination.count;
    },
  });

  return (
    <HeaderTabs
      current={
        current === "list"
          ? `/content/${model.label}`
          : `/content/${model.label}/trash`
      }
      tabs={[
        {
          label: t("list_view.tabs_all", { model: model.verbose_name_plural }),
          to: `/content/${model.label}`,
        },
        {
          label: t("list_view.trash"),
          count: count ?? fetched,
          to: `/content/${model.label}/trash`,
        },
      ]}
    />
  );
}

// The content index route: the list page, or — for singletons, which
// have no list — the editor. While discover loads, the list page's
// spinner covers the wait.
export function ContentIndexPage() {
  const { model: appLabel } = useParams<{ model: string }>();
  const { data: discover } = useDiscover();
  const model = discover?.models.find(R.whereEq({ label: appLabel }));

  return model?.admin.is_singleton ? <ContentEditorPage /> : <ModelListPage />;
}
