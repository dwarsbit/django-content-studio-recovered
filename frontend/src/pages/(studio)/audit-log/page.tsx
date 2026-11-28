import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import relativeTime from "dayjs/plugin/relativeTime";
import { type TFunction } from "i18next";
import * as R from "ramda";
import { type ReactNode, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArrowsDownUpBold,
  PiArrowUUpLeftBold,
  PiClockCounterClockwiseBold,
  PiEyeBold,
  PiEyeSlashBold,
  PiMinusBold,
  PiPencilSimpleBold,
  PiPlusBold,
  PiProhibitBold,
  PiSignInBold,
  PiSignOutBold,
  PiXBold,
} from "react-icons/pi";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ExportMenu } from "@/components/export-menu";
import { Change, Value } from "@/components/form-components/version-dialog";
import { Button } from "@/components/ui/button";
import { DebouncedInput } from "@/components/ui/debounced-input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { PageBody, PageHeader } from "@/components/ui/page-header";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { UserAvatar } from "@/components/ui/user-avatar";
import {
  type AuditAction,
  type AuditChange,
  type AuditEntry,
  type AuditLogOptions,
  type AuditLogQuery,
  type AuditSignIn,
  useAuditLog,
  useAuditLogEnabled,
  useAuditLogExport,
  useAuditVersion,
} from "@/hooks/use-audit-log";
import { useDiscover } from "@/hooks/use-discover";
import { getDownloadErrorMessage } from "@/lib/download";
import { cn, getErrorMessage } from "@/lib/utils";
import type { ExportFormat, Model } from "@/types";

dayjs.extend(relativeTime);
dayjs.extend(localizedFormat);

// Select items cannot have an empty value.
const ALL = "__all__";

const PERIODS = ["today", "7", "30"] as const;
type Period = (typeof PERIODS)[number];

const QUERY_KEYS = ["user", "model", "object", "action", "period", "q"];

/** The filters in the page's URL, so a filtered view can be shared. */
function useQueryParams() {
  const [params, setParams] = useSearchParams();
  const period = (params.get("period") ?? undefined) as Period | undefined;

  const query: AuditLogQuery = {
    user: params.get("user") ?? undefined,
    model: params.get("model") ?? undefined,
    object: params.get("model")
      ? (params.get("object") ?? undefined)
      : undefined,
    action: (params.get("action") ?? undefined) as AuditAction | undefined,
    q: params.get("q") ?? undefined,
    ...periodRange(period),
  };

  function update(changes: Record<string, string | undefined>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);

        for (const [key, value] of Object.entries(changes)) {
          if (value) {
            next.set(key, value);
          } else {
            next.delete(key);
          }
        }

        return next;
      },
      { replace: true },
    );
  }

  function clear() {
    update(Object.fromEntries(QUERY_KEYS.map((key) => [key, undefined])));
  }

  const filtered = QUERY_KEYS.some((key) => params.get(key));

  return { query, period, update, clear, filtered };
}

function periodRange(period: Period | undefined): AuditLogQuery {
  if (!period) {
    return {};
  }

  const days = period === "today" ? 0 : Number(period) - 1;

  // The start of the day here, not on the server.
  return {
    since: dayjs().startOf("day").subtract(days, "day").toISOString(),
  };
}

/**
 * The Audit log page, for superusers: every change made in the admin
 * and every sign-in, newest first, with filters in the URL, the field
 * changes of an update and an export of what the filters show.
 */
export function AuditLogPage() {
  const { t } = useTranslation();
  const enabled = useAuditLogEnabled();
  const { query, period, update, clear, filtered } = useQueryParams();
  const { data, isError, isFetching, fetchNextPage, hasNextPage } =
    useAuditLog(query);
  const { mutateAsync: runExport, isPending: exporting } = useAuditLogExport();
  const [openEntry, setOpenEntry] = useState<AuditChange | null>(null);
  const options = data?.pages[0]?.options;
  const entries = data?.pages.flatMap((page) => page.entries) ?? [];

  async function onExport(format: ExportFormat) {
    try {
      await runExport({ format, query });
    } catch (e) {
      toast.error(await getDownloadErrorMessage(e));
    }
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <PageHeader
        icon={<PiClockCounterClockwiseBold />}
        title={t("audit_log.title")}
        actions={
          enabled &&
          !isError &&
          options && (
            <ExportMenu
              formats={options.export_formats}
              onExport={(format) => void onExport(format)}
              disabled={exporting}
            />
          )
        }
      />
      <PageBody className="space-y-5">
        {isError || !enabled ? (
          <EmptyState
            icon={<PiClockCounterClockwiseBold />}
            title={t("audit_log.unavailable_title")}
            description={t("audit_log.unavailable_description")}
          />
        ) : (
          <section className="rounded-lg border bg-card shadow-xs overflow-hidden">
            <Toolbar
              options={options}
              query={query}
              period={period}
              onChange={update}
            />
            {query.object && query.model && (
              <ObjectFilter
                model={query.model}
                objectId={query.object}
                entries={entries}
                onClear={() => update({ object: undefined })}
              />
            )}
            {!data ? (
              <div aria-busy className="border-t">
                {Array.from({ length: 6 }, (_, idx) => (
                  <div key={idx} className="px-4 py-3 flex gap-3">
                    <div className="size-8 rounded-full bg-muted animate-pulse" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
                      <div className="h-2.5 w-1/2 rounded bg-muted animate-pulse" />
                    </div>
                  </div>
                ))}
              </div>
            ) : entries.length === 0 && !hasNextPage ? (
              <EmptyState
                className="border-t py-10"
                icon={<PiClockCounterClockwiseBold />}
                title={
                  filtered
                    ? t("audit_log.no_matches_title")
                    : t("audit_log.empty_title")
                }
                description={
                  filtered
                    ? t("audit_log.no_matches_description")
                    : t("audit_log.empty_description")
                }
                action={
                  filtered && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={clear}
                    >
                      {t("audit_log.clear_filters")}
                    </Button>
                  )
                }
              />
            ) : (
              <Timeline entries={entries} onOpen={setOpenEntry} />
            )}
            {data && (entries.length > 0 || hasNextPage) && (
              <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground flex items-center gap-3">
                <span className="flex-1">
                  {options?.keep_days
                    ? t("audit_log.showing_days", {
                        count: entries.length,
                        days: options.keep_days,
                      })
                    : t("audit_log.showing", { count: entries.length })}
                </span>
                {hasNextPage && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isFetching}
                    onClick={() => void fetchNextPage()}
                  >
                    {isFetching && <Spinner className="size-4" />}
                    {t("audit_log.load_more")}
                  </Button>
                )}
              </div>
            )}
          </section>
        )}
      </PageBody>
      <ChangeDialog entry={openEntry} onClose={() => setOpenEntry(null)} />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  allLabel,
  items,
  onChange,
}: {
  label: string;
  value: string | undefined;
  allLabel: string;
  items: { value: string; label: string }[];
  onChange: (value: string | undefined) => void;
}) {
  return (
    <Select
      value={value ?? ALL}
      onValueChange={(next) => onChange(next === ALL ? undefined : next)}
    >
      <SelectTrigger size="sm" className="w-auto max-w-full" aria-label={label}>
        <span className="text-muted-foreground">{label}:</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent align="end">
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Toolbar({
  options,
  query,
  period,
  onChange,
}: {
  options?: AuditLogOptions;
  query: AuditLogQuery;
  period?: Period;
  onChange: (changes: Record<string, string | undefined>) => void;
}) {
  const { t } = useTranslation();
  const actions = options?.actions ?? [];
  const models = options?.models ?? [];
  const users = options?.users ?? [];

  // The filtered value stays listed while the options load.
  const withCurrent = (
    items: { value: string; label: string }[],
    value: string | undefined,
  ) =>
    value && !items.some((item) => item.value === value)
      ? [...items, { value, label: value }]
      : items;

  return (
    <div className="px-4 py-3 space-y-3">
      <div>
        <h2 className="font-semibold">{t("audit_log.list_title")}</h2>
        <div className="text-xs text-muted-foreground">
          {t("audit_log.list_description")}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <DebouncedInput
          type="search"
          value={query.q ?? ""}
          onChange={(q) => {
            if (q !== (query.q ?? "")) {
              onChange({ q: q || undefined });
            }
          }}
          placeholder={t("audit_log.search")}
          aria-label={t("audit_log.search")}
          className="h-8 w-full sm:w-64"
        />
        <div className="flex-1" />
        <FilterSelect
          label={t("audit_log.filters.action")}
          allLabel={t("audit_log.filters.all_actions")}
          value={query.action}
          items={withCurrent(
            actions.map((action) => ({
              value: action,
              label: t(`audit_log.actions.${action}`),
            })),
            query.action,
          )}
          onChange={(action) => onChange({ action })}
        />
        <FilterSelect
          label={t("audit_log.filters.user")}
          allLabel={t("audit_log.filters.all_users")}
          value={query.user}
          items={withCurrent(users, query.user)}
          onChange={(user) => onChange({ user })}
        />
        <FilterSelect
          label={t("audit_log.filters.model")}
          allLabel={t("audit_log.filters.all_models")}
          value={query.model}
          items={withCurrent(
            models.map((model) => ({
              ...model,
              label: capfirst(model.label),
            })),
            query.model,
          )}
          onChange={(model) => onChange({ model, object: undefined })}
        />
        <FilterSelect
          label={t("audit_log.filters.period")}
          allLabel={t("audit_log.periods.all")}
          value={period}
          items={PERIODS.map((value) => ({
            value,
            label: t(`audit_log.periods.${value}`),
          }))}
          onChange={(value) => onChange({ period: value })}
        />
      </div>
    </div>
  );
}

/** The object the list is narrowed to, from an Activity card's View all. */
function ObjectFilter({
  model,
  objectId,
  entries,
  onClear,
}: {
  model: string;
  objectId: string;
  entries: AuditEntry[];
  onClear: () => void;
}) {
  const { t } = useTranslation();
  const name =
    entries.find(
      (entry): entry is AuditChange =>
        entry.kind === "change" &&
        entry.model === model &&
        entry.object_id === objectId,
    )?.object_repr ?? `#${objectId}`;

  return (
    <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground flex items-center gap-2">
      <span className="flex-1 min-w-0 truncate">
        {t("audit_log.object_filter", { name })}
      </span>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 px-2"
        onClick={onClear}
        aria-label={t("audit_log.object_filter_clear")}
      >
        <PiXBold />
        {t("audit_log.object_filter_clear")}
      </Button>
    </div>
  );
}

function capfirst(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The entries per day (YYYY-MM-DD, local time), newest first. */
function groupByDay(entries: AuditEntry[]): [string, AuditEntry[]][] {
  const days = new Map<string, AuditEntry[]>();

  for (const entry of entries) {
    const day = dayjs(entry.time).format("YYYY-MM-DD");
    days.set(day, [...(days.get(day) ?? []), entry]);
  }

  return [...days.entries()];
}

function dayLabel(day: string, t: TFunction): string {
  const date = dayjs(day);

  if (date.isSame(dayjs(), "day")) {
    return t("audit_log.today");
  }
  if (date.isSame(dayjs().subtract(1, "day"), "day")) {
    return t("audit_log.yesterday");
  }
  return date.format("LL");
}

function Timeline({
  entries,
  onOpen,
}: {
  entries: AuditEntry[];
  onOpen: (entry: AuditChange) => void;
}) {
  const { t } = useTranslation();

  return (
    <ul className="border-t">
      {groupByDay(entries).map(([day, items]) => (
        <li key={day}>
          <div className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {dayLabel(day, t)}
          </div>
          <ul>
            {items.map((entry) =>
              entry.kind === "change" ? (
                <ChangeRow key={entry.id} entry={entry} onOpen={onOpen} />
              ) : (
                <SignInRow key={entry.id} entry={entry} />
              ),
            )}
          </ul>
        </li>
      ))}
    </ul>
  );
}

const ACTION_ICONS: Record<AuditAction, typeof PiPlusBold> = {
  created: PiPlusBold,
  updated: PiPencilSimpleBold,
  deleted: PiMinusBold,
  restored: PiArrowUUpLeftBold,
  reordered: PiArrowsDownUpBold,
  published: PiEyeBold,
  unpublished: PiEyeSlashBold,
  signed_in: PiSignInBold,
  sign_in_failed: PiProhibitBold,
  signed_out: PiSignOutBold,
};

const ACTION_COLORS: Record<AuditAction, string> = {
  created: "bg-success",
  updated: "bg-sky-500",
  deleted: "bg-destructive",
  restored: "bg-success",
  reordered: "bg-sky-500",
  published: "bg-violet-500",
  unpublished: "bg-zinc-500",
  signed_in: "bg-emerald-600",
  sign_in_failed: "bg-destructive",
  signed_out: "bg-zinc-500",
};

/** The kind of entry, on the corner of the avatar. */
function ActionBadge({ action }: { action: AuditAction }) {
  const Icon = ACTION_ICONS[action] ?? PiPencilSimpleBold;

  return (
    <span
      aria-hidden
      className={cn(
        "absolute -right-1 -bottom-1 size-4 rounded-full border-2 border-card flex items-center justify-center text-white",
        ACTION_COLORS[action] ?? "bg-sky-500",
      )}
    >
      <Icon className="size-2" />
    </span>
  );
}

function Time({ value }: { value: string }) {
  const time = dayjs(value);

  return (
    <time
      dateTime={value}
      title={time.format("LLL")}
      className="text-xs text-muted-foreground tabular-nums shrink-0"
    >
      {time.isSame(dayjs(), "day") ? time.fromNow() : time.format("LT")}
    </time>
  );
}

function Row({
  name,
  action,
  children,
  details,
  time,
  onClick,
  title,
}: {
  name: string;
  action: AuditAction;
  children: ReactNode;
  details: ReactNode;
  time: string;
  onClick?: () => void;
  title?: string;
}) {
  const content = (
    <>
      <span className="relative shrink-0 mt-0.5">
        <UserAvatar name={name} className="size-8" />
        <ActionBadge action={action} />
      </span>
      <div className="flex-1 min-w-0">
        <div className="break-words">{children}</div>
        <div className="text-xs text-muted-foreground flex flex-wrap gap-x-2 gap-y-0.5 min-w-0">
          {details}
        </div>
      </div>
      <Time value={time} />
    </>
  );

  return (
    <li data-action={action}>
      {onClick ? (
        <div
          role="button"
          tabIndex={0}
          title={title}
          className="w-full text-left px-4 py-2 flex items-start gap-3 hover:bg-muted/50 focus-visible:bg-muted/50 outline-none cursor-pointer"
          onClick={onClick}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onClick();
            }
          }}
        >
          {content}
        </div>
      ) : (
        <div className="px-4 py-2 flex items-start gap-3">{content}</div>
      )}
    </li>
  );
}

function ChangeRow({
  entry,
  onOpen,
}: {
  entry: AuditChange;
  onOpen: (entry: AuditChange) => void;
}) {
  const { t } = useTranslation();
  const { data: discover } = useDiscover();
  const model = discover?.models?.find(R.whereEq({ label: entry.model }));
  const user = entry.user?.label ?? t("audit_log.unknown_user");
  const linked = entry.object_exists && model && !model.inline_only;

  return (
    <Row
      name={user}
      action={entry.action}
      time={entry.time}
      onClick={entry.has_version ? () => onOpen(entry) : undefined}
      title={entry.has_version ? t("audit_log.open_change") : undefined}
      details={
        <>
          <span className="first-letter:uppercase">
            {model?.verbose_name ?? entry.model_name}
          </span>
          {entry.message && <span>{entry.message}</span>}
        </>
      }
    >
      <span className="font-medium">{user}</span>{" "}
      <span className="text-muted-foreground">
        {t(`audit_log.verbs.${entry.action}`)}
      </span>{" "}
      {linked ? (
        <Link
          className="font-medium hover:underline"
          to={`/content/${entry.model}/${entry.object_id}`}
          onClick={(event) => event.stopPropagation()}
        >
          {entry.object_repr}
        </Link>
      ) : (
        <span className="font-medium">{entry.object_repr}</span>
      )}
    </Row>
  );
}

function SignInRow({ entry }: { entry: AuditSignIn }) {
  const { t } = useTranslation();
  const user =
    entry.user?.label || entry.username || t("audit_log.unknown_user");
  const method = entry.method
    ? t(`audit_log.methods.${entry.method}`, { defaultValue: entry.method })
    : null;

  return (
    <Row
      name={user}
      action={entry.action}
      time={entry.time}
      details={
        <>
          {entry.reason && (
            <span className="text-destructive">
              {t(`audit_log.reasons.${entry.reason}`, {
                defaultValue: entry.reason,
              })}
            </span>
          )}
          {method && <span>{method}</span>}
          {entry.ip_address && (
            <span className="tabular-nums">{entry.ip_address}</span>
          )}
          {entry.browser && (
            <span title={entry.user_agent}>{entry.browser}</span>
          )}
        </>
      }
    >
      <span className="font-medium">{user}</span>{" "}
      <span className="text-muted-foreground">
        {t(`audit_log.verbs.${entry.action}`)}
      </span>
      {!entry.user && entry.action === "sign_in_failed" && (
        <span className="text-muted-foreground">
          {" "}
          {t("audit_log.no_such_user")}
        </span>
      )}
    </Row>
  );
}

/**
 * What a change did, field by field, from the version the history app
 * kept. Read-only: restoring happens on the object's edit page.
 */
function ChangeDialog({
  entry,
  onClose,
}: {
  entry: AuditChange | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { data: discover } = useDiscover();
  const { data: version, error } = useAuditVersion(entry?.entry_id ?? null);
  const model: Model | undefined = discover?.models?.find(
    R.whereEq({ label: entry?.model }),
  );
  const created = version?.fields.length === 0;
  const shown = useMemo(() => {
    if (!version || !model) {
      return [];
    }

    return created
      ? Object.keys(version.data).filter(
          (name) =>
            model.fields[name] &&
            !R.isNil(version.data[name]) &&
            !R.isEmpty(version.data[name]),
        )
      : version.fields.filter((name) => model.fields[name]);
  }, [version, model, created]);
  const linked = version?.object_exists && model && !model.inline_only;

  return (
    <Dialog open={entry !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] grid-rows-[auto_minmax(0,1fr)_auto]">
        <DialogHeader>
          <DialogTitle>
            {entry
              ? `${entry.object_repr} · ${dayjs(entry.time).format("LLL")}`
              : t("history.loading")}
          </DialogTitle>
          <DialogDescription>
            {entry &&
              [
                entry.user?.label,
                created ? t("history.created") : entry.message,
              ]
                .filter(Boolean)
                .join(" · ")}
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto scrollbar -mx-6 px-6">
          {error ? (
            <div className="text-sm text-destructive">
              {getErrorMessage(error)}
            </div>
          ) : !version ? (
            <div className="py-6 flex items-center justify-center">
              <Spinner />
            </div>
          ) : !model || R.isEmpty(shown) ? (
            <div className="text-sm text-muted-foreground">
              {t("history.no_changes")}
            </div>
          ) : (
            <dl className="divide-y" data-testid="version-fields">
              {shown.map((name) => (
                <div key={name} className="py-3 first:pt-0">
                  <dt className="text-sm font-medium mb-1.5">
                    {capfirst(model.fields[name].verbose_name ?? name)}
                  </dt>
                  <dd className="min-w-0">
                    {created ? (
                      <Value
                        field={model.fields[name]}
                        value={version.data[name]}
                      />
                    ) : (
                      <Change
                        field={model.fields[name]}
                        before={version.previous[name]}
                        after={version.data[name]}
                      />
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        <DialogFooter>
          {version && !version.object_exists && (
            <span className="text-xs text-muted-foreground mr-auto self-center">
              {t("audit_log.object_deleted")}
            </span>
          )}
          <Button variant="outline" onClick={onClose}>
            {t("history.close")}
          </Button>
          {linked && entry && (
            <Button asChild>
              <Link to={`/content/${entry.model}/${entry.object_id}`}>
                {t("audit_log.open_object")}
              </Link>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
