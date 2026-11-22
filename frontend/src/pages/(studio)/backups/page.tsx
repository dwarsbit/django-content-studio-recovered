import { useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArchiveBold,
  PiArrowLeftBold,
  PiCalendarBlankBold,
  PiClockCounterClockwiseBold,
  PiDatabaseBold,
  PiDotsThreeBold,
  PiDownloadSimpleBold,
  PiHardDrivesBold,
  PiTerminalWindowBold,
  PiUploadSimpleBold,
  PiWarningBold,
} from "react-icons/pi";
import { Link } from "react-router";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { PageBody, PageHeader } from "@/components/ui/page-header";
import { Spinner } from "@/components/ui/spinner";
import {
  activeRestore,
  type Backup,
  type Backups,
  isBackingUp,
  type Restore,
  useBackUpNow,
  useBackups,
  useBackupsEnabled,
  useDownloadBackup,
} from "@/hooks/use-backups";
import { useStatusEnabled } from "@/hooks/use-status";
import { getDownloadErrorMessage } from "@/lib/download";
import { cn, getErrorMessage } from "@/lib/utils";

import { formatBytes, formatSeconds } from "./_components/format";
import {
  RestoreDialog,
  type RestoreSource,
} from "./_components/restore-dialog";

dayjs.extend(relativeTime);

/**
 * The Backups page, for superusers: the database backups with their
 * files to download, Back up now, and restoring a backup or a file.
 */
export function BackupsPage() {
  const { t } = useTranslation();
  const enabled = useBackupsEnabled();
  const statusEnabled = useStatusEnabled();
  const { data, isError } = useBackups();
  const backUpNow = useBackUpNow();
  const busy = isBackingUp(data);
  const restoring = activeRestore(data);
  const restoreInfo = data?.restore;
  const canRestore = restoreInfo?.enabled === true;
  const [source, setSource] = useState<RestoreSource | null>(null);

  useRestoreFinished(data);

  async function onBackUpNow() {
    try {
      await backUpNow.mutateAsync();
      toast.success(t("backups.started"));
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <PageHeader
        back={
          statusEnabled ? (
            <Button
              asChild
              size="icon-sm"
              variant="ghost"
              className="-ml-2 text-muted-foreground"
              aria-label={t("backups.back")}
            >
              <Link to="/status">
                <PiArrowLeftBold />
              </Link>
            </Button>
          ) : undefined
        }
        icon={<PiArchiveBold />}
        title={t("backups.title")}
        actions={
          enabled &&
          !isError && (
            <div className="flex items-center gap-2">
              <Button
                disabled={busy || !!restoring || backUpNow.isPending || !data}
                onClick={() => void onBackUpNow()}
              >
                {busy || backUpNow.isPending ? (
                  <Spinner className="size-4" />
                ) : (
                  <PiArchiveBold />
                )}
                {busy ? t("backups.running") : t("backups.back_up_now")}
              </Button>
              {canRestore && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label={t("backups.more_actions")}
                    >
                      <PiDotsThreeBold />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      disabled={busy || !!restoring}
                      onSelect={() => setSource({ kind: "file" })}
                    >
                      <PiUploadSimpleBold />
                      {t("backups.restore_from_file")}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          )
        }
      />
      <PageBody className="space-y-5">
        {isError || !enabled ? (
          <EmptyState
            icon={<PiArchiveBold />}
            title={t("backups.unavailable_title")}
            description={t("backups.unavailable_description")}
          />
        ) : (
          <>
            {restoring && (
              <Alert variant="warning">
                <Spinner className="size-4" />
                <AlertTitle>
                  {t("backups.restoring", {
                    name: restoring.name,
                    database: restoring.database,
                  })}
                </AlertTitle>
                <AlertDescription>
                  {t("backups.restoring_hint")}
                </AlertDescription>
              </Alert>
            )}
            <Settings data={data} />
            <BackupList
              data={data}
              onRestore={
                canRestore
                  ? (backup) => setSource({ kind: "backup", backup })
                  : undefined
              }
              restoreLocked={busy || !!restoring}
            />
            {data && (data.restores?.length ?? 0) > 0 && (
              <RestoreList restores={data.restores ?? []} />
            )}
            {restoreInfo && canRestore && (
              <RestoreDialog
                source={source}
                info={restoreInfo}
                onClose={() => setSource(null)}
              />
            )}
          </>
        )}
      </PageBody>
    </div>
  );
}

/** When backups run, how many are kept and where they are. */
function Settings({ data }: { data?: Backups }) {
  const { t } = useTranslation();

  if (!data) {
    return (
      <section
        aria-busy
        className="rounded-lg border bg-card shadow-xs h-[74px] animate-pulse"
      />
    );
  }

  const next = data.next_run_at ? dayjs(data.next_run_at).fromNow() : null;

  return (
    <section className="rounded-lg border bg-card shadow-xs px-4 py-3 grid gap-3 sm:grid-cols-3">
      <Fact icon={<PiCalendarBlankBold />} label={t("backups.schedule")}>
        {data.schedule
          ? next
            ? t("backups.schedule_next", { schedule: data.schedule, next })
            : data.schedule
          : t("backups.not_scheduled")}
      </Fact>
      <Fact icon={<PiDatabaseBold />} label={t("backups.kept")}>
        {data.keep
          ? t("backups.keep", { count: data.keep })
          : t("backups.keep_all")}
      </Fact>
      <Fact icon={<PiHardDrivesBold />} label={t("backups.storage")}>
        {data.storage
          ? `${data.storage} · ${data.folder}`
          : t("backups.no_storage")}
      </Fact>
    </section>
  );
}

function Fact({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 min-w-0">
      <span
        aria-hidden
        className="size-8 shrink-0 rounded-md border bg-muted text-muted-foreground flex items-center justify-center [&_svg]:size-4"
      >
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-sm font-medium break-words">{children}</div>
      </div>
    </div>
  );
}

/**
 * Tell when a restore that was running ends, and load everything again
 * once the database holds other data.
 */
function useRestoreFinished(data?: Backups) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const running = useRef<number | null>(null);

  useEffect(() => {
    const active = activeRestore(data);

    if (active) {
      running.current = active.id;
      return;
    }

    if (running.current === null) {
      return;
    }

    const ended = data?.restores?.find(
      (restore) => restore.id === running.current,
    );

    running.current = null;

    if (ended?.status === "done") {
      toast.success(
        t("backups.restore.done", {
          name: ended.name,
          database: ended.database,
        }),
      );
      void queryClient.invalidateQueries();
    } else if (ended?.status === "failed") {
      toast.error(t("backups.restore.failed", { error: ended.error ?? "" }));
    }
  }, [data, queryClient, t]);
}

function BackupList({
  data,
  onRestore,
  restoreLocked,
}: {
  data?: Backups;
  // Set when the signed-in user may restore on this page.
  onRestore?: (backup: Backup) => void;
  restoreLocked: boolean;
}) {
  const { t } = useTranslation();

  return (
    <section className="rounded-lg border bg-card shadow-xs overflow-hidden">
      <div className="px-4 py-3">
        <h2 className="font-semibold">{t("backups.list.title")}</h2>
        <div className="text-xs text-muted-foreground">
          {t("backups.list.description")}
        </div>
      </div>
      {!data ? (
        <div aria-busy className="border-t">
          {Array.from({ length: 3 }, (_, idx) => (
            <div key={idx} className="px-4 py-3 space-y-1.5">
              <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
              <div className="h-2.5 w-1/2 rounded bg-muted animate-pulse" />
            </div>
          ))}
        </div>
      ) : data.backups.length === 0 ? (
        <EmptyState
          className="border-t py-10"
          icon={<PiArchiveBold />}
          title={t("backups.list.empty_title")}
          description={t("backups.list.empty_description")}
        />
      ) : (
        <ul>
          {data.backups.map((backup) => (
            <BackupRow
              key={backup.id}
              backup={backup}
              onRestore={onRestore}
              restoreLocked={restoreLocked}
            />
          ))}
        </ul>
      )}
      <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground flex items-center gap-1.5">
        <PiTerminalWindowBold className="shrink-0" />
        <span>
          {onRestore ? t("backups.restore_note") : t("backups.restore_hint")}{" "}
          <code className="font-mono">manage.py content_studio_restore</code>
        </span>
      </div>
    </section>
  );
}

const STATUS_DOT: Record<Backup["status"], string> = {
  queued: "bg-muted-foreground/60",
  running: "",
  done: "bg-success",
  failed: "bg-destructive",
};

function BackupRow({
  backup,
  onRestore,
  restoreLocked,
}: {
  backup: Backup;
  onRestore?: (backup: Backup) => void;
  restoreLocked: boolean;
}) {
  const { t } = useTranslation();
  const download = useDownloadBackup();
  const when = dayjs(backup.finished_at ?? backup.created_at);

  async function onDownload() {
    try {
      await download.mutateAsync(backup);
    } catch (e) {
      toast.error(await getDownloadErrorMessage(e));
    }
  }

  return (
    <li
      data-status={backup.status}
      className="border-t px-4 py-3 flex items-start gap-3"
    >
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            className="font-medium"
            title={when.format("YYYY-MM-DD HH:mm:ss")}
          >
            {when.format("D MMM YYYY, HH:mm")}
          </span>
          <Badge variant="outline" className="font-normal">
            {backup.database}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>
            {backup.created_by &&
            (backup.trigger === "manual" || backup.trigger === "before_restore")
              ? t("backups.by", {
                  trigger: t(`backups.trigger.${backup.trigger}`),
                  user: backup.created_by,
                })
              : t(`backups.trigger.${backup.trigger}`)}
          </span>
          <span>{when.fromNow()}</span>
          {backup.size != null && <span>{formatBytes(backup.size)}</span>}
          {backup.duration != null && (
            <span>{formatSeconds(backup.duration)}</span>
          )}
          {backup.name && (
            <span className="font-mono break-all">{backup.name}</span>
          )}
        </div>
        {backup.error && backup.status === "failed" && (
          <div className="text-xs text-destructive break-words">
            {backup.error}
          </div>
        )}
        {backup.status === "done" && backup.skipped?.length > 0 && (
          <div
            className="text-xs text-muted-foreground break-words"
            title={t("backups.skipped_hint")}
          >
            {t("backups.skipped", {
              count: backup.skipped.length,
              models: backup.skipped.join(", "),
            })}
          </div>
        )}
      </div>
      <Badge variant="secondary" className="gap-1.5 pl-1.5 shrink-0 mt-0.5">
        {backup.status === "running" ? (
          <Spinner className="size-3" />
        ) : (
          <span
            className={cn("size-1.5 rounded-full", STATUS_DOT[backup.status])}
          />
        )}
        {t(`backups.status.${backup.status}`)}
      </Badge>
      {backup.status === "done" && (
        <Button
          variant="outline"
          size="icon"
          className="shrink-0"
          aria-label={t("backups.download", { name: backup.name })}
          disabled={download.isPending}
          onClick={() => void onDownload()}
        >
          {download.isPending ? (
            <Spinner className="size-4" />
          ) : (
            <PiDownloadSimpleBold />
          )}
        </Button>
      )}
      {backup.status === "done" && onRestore && (
        <Button
          variant="outline"
          size="icon"
          className="shrink-0"
          aria-label={t("backups.restore_item", { name: backup.name })}
          title={t("backups.restore_item", { name: backup.name })}
          disabled={restoreLocked}
          onClick={() => onRestore(backup)}
        >
          <PiClockCounterClockwiseBold />
        </Button>
      )}
    </li>
  );
}

const RESTORE_DOT: Record<Restore["status"], string> = {
  pending: "bg-muted-foreground/60",
  queued: "bg-muted-foreground/60",
  running: "",
  done: "bg-success",
  failed: "bg-destructive",
};

/** The latest restores, newest first. */
function RestoreList({ restores }: { restores: Restore[] }) {
  const { t } = useTranslation();

  return (
    <section className="rounded-lg border bg-card shadow-xs overflow-hidden">
      <div className="px-4 py-3">
        <h2 className="font-semibold">{t("backups.restores.title")}</h2>
        <div className="text-xs text-muted-foreground">
          {t("backups.restores.description")}
        </div>
      </div>
      <ul>
        {restores.map((restore) => {
          const when = dayjs(restore.finished_at ?? restore.created_at);

          return (
            <li
              key={restore.id}
              data-status={restore.status}
              className="border-t px-4 py-3 flex items-start gap-3"
            >
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span
                    className="font-medium"
                    title={when.format("YYYY-MM-DD HH:mm:ss")}
                  >
                    {when.format("D MMM YYYY, HH:mm")}
                  </span>
                  <Badge variant="outline" className="font-normal">
                    {restore.database}
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {restore.created_by
                      ? t("backups.restores.by", {
                          source: t(
                            `backups.restores.source.${restore.source}`,
                          ),
                          user: restore.created_by,
                        })
                      : t(`backups.restores.source.${restore.source}`)}
                  </span>
                  <span>{when.fromNow()}</span>
                  {restore.rows != null && (
                    <span>
                      {t("backups.restores.rows", { count: restore.rows })}
                    </span>
                  )}
                  {restore.duration != null && (
                    <span>{formatSeconds(restore.duration)}</span>
                  )}
                  <span className="font-mono break-all">{restore.name}</span>
                </div>
                {restore.safety_backup && (
                  <div className="text-xs text-muted-foreground break-all">
                    {t("backups.restores.safety", {
                      name: restore.safety_backup,
                    })}
                  </div>
                )}
                {restore.error && restore.status === "failed" && (
                  <div className="text-xs text-destructive break-words flex items-start gap-1">
                    <PiWarningBold className="shrink-0 mt-0.5" />
                    {restore.error}
                  </div>
                )}
              </div>
              <Badge
                variant="secondary"
                className="gap-1.5 pl-1.5 shrink-0 mt-0.5"
              >
                {restore.status === "running" ? (
                  <Spinner className="size-3" />
                ) : (
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      RESTORE_DOT[restore.status],
                    )}
                  />
                )}
                {t(`backups.restores.status.${restore.status}`)}
              </Badge>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
