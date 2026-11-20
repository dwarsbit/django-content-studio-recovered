import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArrowsClockwiseBold,
  PiCheckCircleBold,
  PiClockBold,
  PiCubeBold,
  PiPlayCircleBold,
  PiPulseBold,
  PiRepeatBold,
  PiStackBold,
  PiWarningBold,
  PiXCircleBold,
} from "react-icons/pi";
import { Link } from "react-router";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageBody, PageHeader } from "@/components/ui/page-header";
import { Spinner } from "@/components/ui/spinner";
import {
  type RecurringTask,
  type ServiceStatus,
  type StatusService,
  type StatusTask,
  type StatusTasks,
  type SystemStatus,
  useRefreshStatus,
  useStatusEnabled,
  useStatusTasks,
  useSystemStatus,
} from "@/hooks/use-status";
import { cn } from "@/lib/utils";

dayjs.extend(relativeTime);

type TaskFilter = "all" | "pending" | "finished";

const DOT: Record<ServiceStatus, string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  down: "bg-destructive",
  unknown: "bg-muted-foreground/60",
};

const MESSAGE: Record<ServiceStatus, string> = {
  ok: "text-muted-foreground",
  degraded: "text-warning",
  down: "text-destructive",
  unknown: "text-muted-foreground",
};

/** The time now, updated so that "12 seconds ago" keeps counting. */
function useNow(interval = 10_000) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), interval);

    return () => clearInterval(timer);
  }, [interval]);

  return now;
}

/** A check's time: "3 ms" or "2.4 s". */
function formatElapsed(ms: number) {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** A run's time: "42 s", "3 min" or "1 h 5 min". */
function formatSeconds(seconds: number) {
  if (seconds < 60) {
    return `${seconds} s`;
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)} min`;
  }

  return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
}

/**
 * The system status page, opened from the user menu: the services the
 * site depends on, the tasks that wait, run or finished, and the
 * recurring tasks. Services are checked when the page opens and on
 * Refresh; the tasks keep themselves up to date.
 */
export function StatusPage() {
  const { t } = useTranslation();
  const enabled = useStatusEnabled();
  const { data: status, isError } = useSystemStatus();
  const { data: tasks } = useStatusTasks();
  const refresh = useRefreshStatus();
  const now = useNow();

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <PageHeader
        icon={<PiPulseBold />}
        title={t("status.title")}
        actions={
          <>
            {status && (
              <span className="text-sm text-muted-foreground max-sm:hidden">
                {t("status.checked", {
                  when: dayjs(status.checked_at).from(dayjs(now)),
                })}
              </span>
            )}
            <Button
              variant="outline"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
            >
              <PiArrowsClockwiseBold
                className={cn(refresh.isPending && "animate-spin")}
              />
              {t("status.refresh")}
            </Button>
          </>
        }
      />
      <PageBody className="space-y-5">
        {isError || !enabled ? (
          <EmptyState
            icon={<PiPulseBold />}
            title={t("status.unavailable_title")}
            description={t("status.unavailable_description")}
          />
        ) : (
          <>
            <Overview status={status} tasks={tasks} />
            <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] items-start">
              <Services status={status} />
              <div className="space-y-5 min-w-0">
                <RecentTasks tasks={tasks} now={now} />
                <RecurringTasks tasks={tasks} now={now} />
              </div>
            </div>
          </>
        )}
      </PageBody>
    </div>
  );
}

function Card({
  title,
  description,
  aside,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border bg-card shadow-xs overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold">{title}</h2>
          {description && (
            <div className="text-xs text-muted-foreground">{description}</div>
          )}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-busy className="border-t">
      {Array.from({ length: rows }, (_, idx) => (
        <div key={idx} className="flex items-center gap-3 px-4 py-3">
          <div className="size-8 rounded-md bg-muted animate-pulse" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
            <div className="h-2.5 w-1/2 rounded bg-muted animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

function operational(services: StatusService[]) {
  // Services that are not checked are not counted.
  const checked = services.filter((service) => service.status !== "unknown");

  return {
    ok: checked.filter((service) => service.status === "ok").length,
    total: checked.length,
  };
}

/** The verdict in one card, with the three numbers that back it. */
function Overview({
  status,
  tasks,
}: {
  status?: SystemStatus;
  tasks?: StatusTasks;
}) {
  const { t } = useTranslation();

  if (!status) {
    return (
      <section
        aria-busy
        className="rounded-lg border bg-card shadow-xs h-[86px] animate-pulse"
      />
    );
  }

  const { ok, total } = operational(status.services);
  const troubled = status.services.filter(
    (service) => service.status === "down" || service.status === "degraded",
  );
  const failed = tasks?.counts.failed ?? 0;
  const Icon =
    status.status === "down"
      ? PiXCircleBold
      : status.status === "degraded"
        ? PiWarningBold
        : PiCheckCircleBold;

  const title =
    status.status === "down"
      ? t("status.overview.down", {
          count: troubled.filter((s) => s.status === "down").length,
        })
      : status.status === "degraded"
        ? t("status.overview.degraded", { count: troubled.length })
        : t("status.overview.ok");

  const lines = [
    troubled.length > 0
      ? troubled
          .slice(0, 2)
          .map((service) =>
            service.message
              ? `${service.label}: ${service.message}`
              : `${service.label}.`,
          )
          .join(" ")
      : t("status.overview.ok_description"),
    failed > 0 ? t("status.overview.failed_tasks", { count: failed }) : null,
  ].filter(Boolean);

  return (
    <section
      data-status={status.status}
      className="rounded-lg border bg-card shadow-xs px-4 py-4 flex flex-wrap items-center gap-x-6 gap-y-4"
    >
      <div className="flex items-center gap-3 flex-1 min-w-64">
        <span
          className={cn(
            "size-10 shrink-0 rounded-full flex items-center justify-center [&_svg]:size-5",
            status.status === "down"
              ? "bg-destructive/10 text-destructive"
              : status.status === "degraded"
                ? "bg-warning/15 text-warning"
                : "bg-success/10 text-success",
          )}
        >
          <Icon />
        </span>
        <div className="min-w-0">
          <div className="text-base font-semibold">{title}</div>
          <div className="text-sm text-muted-foreground">{lines.join(" ")}</div>
        </div>
      </div>
      <dl className="flex divide-x">
        <Figure
          value={t("status.of", { count: ok, total })}
          label={t("status.figures.services")}
        />
        <Figure
          value={tasks ? String(tasks.counts.pending) : "–"}
          label={t("status.figures.pending")}
        />
        <Figure
          value={tasks ? String(tasks.counts.failed) : "–"}
          label={t("status.figures.failed")}
        />
      </dl>
    </section>
  );
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="px-4 first:pl-0 last:pr-0 sm:first:pl-4 sm:first:border-l">
      <dd className="text-base font-semibold tabular-nums">{value}</dd>
      <dt className="text-xs text-muted-foreground">{label}</dt>
    </div>
  );
}

function Services({ status }: { status?: SystemStatus }) {
  const { t } = useTranslation();
  const groups: { name: string; services: StatusService[] }[] = [];

  for (const service of status?.services ?? []) {
    const group = groups.find((candidate) => candidate.name === service.group);

    if (group) {
      group.services.push(service);
    } else {
      groups.push({ name: service.group, services: [service] });
    }
  }

  const counts = status ? operational(status.services) : null;

  return (
    <Card
      title={t("status.services.title")}
      description={t("status.services.description")}
      aside={
        counts && (
          <span className="text-xs text-muted-foreground shrink-0 pt-0.5">
            {t("status.services.operational", {
              count: counts.ok,
              total: counts.total,
            })}
          </span>
        )
      }
    >
      {!status ? (
        <Loading rows={6} />
      ) : (
        groups.map((group) => (
          <div key={group.name} role="group" aria-label={group.name}>
            {group.name && (
              <div className="border-t bg-muted/50 px-4 py-1.5 text-xs font-medium text-muted-foreground">
                {group.name}
              </div>
            )}
            <ul>
              {group.services.map((service) => (
                <ServiceRow key={service.key} service={service} />
              ))}
            </ul>
          </div>
        ))
      )}
    </Card>
  );
}

function ServiceRow({ service }: { service: StatusService }) {
  const { t } = useTranslation();
  const detail = [
    service.detail,
    // How long the check took, when it is worth a number.
    (service.status === "ok" || service.status === "degraded") &&
    service.duration > 0
      ? formatElapsed(service.duration)
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li
      data-status={service.status}
      className="border-t px-4 py-3 flex items-start gap-3"
    >
      <span
        aria-hidden
        className="size-8 shrink-0 rounded-md border bg-muted text-muted-foreground flex items-center justify-center [&_svg]:size-4 [&_span]:text-base"
      >
        {service.icon ? <span className={service.icon} /> : <PiCubeBold />}
      </span>
      <div className="flex-1 min-w-0">
        <div className="font-medium">
          <ServiceLabel service={service} />
        </div>
        {detail && (
          <div className="text-xs text-muted-foreground">{detail}</div>
        )}
        {service.message && (
          <div className={cn("text-xs mt-0.5", MESSAGE[service.status])}>
            {service.message}
          </div>
        )}
      </div>
      <Badge variant="secondary" className="gap-1.5 pl-1.5 shrink-0 mt-0.5">
        <span className={cn("size-1.5 rounded-full", DOT[service.status])} />
        {t(`status.service_status.${service.status}`)}
      </Badge>
    </li>
  );
}

/** A service's name: a link when it has a url. */
function ServiceLabel({ service }: { service: StatusService }) {
  if (!service.url) {
    return service.label;
  }

  const className =
    "underline-offset-4 hover:underline outline-none focus-visible:underline";

  return /^https?:\/\//i.test(service.url) ? (
    <a
      href={service.url}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
    >
      {service.label}
    </a>
  ) : (
    <Link to={`/${service.url.replace(/^\//, "")}`} className={className}>
      {service.label}
    </Link>
  );
}

function RecentTasks({ tasks, now }: { tasks?: StatusTasks; now: number }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<TaskFilter>("all");

  if (tasks && !tasks.connected) {
    return (
      <Card
        title={t("status.tasks.title")}
        description={t("status.tasks.description")}
      >
        <EmptyState
          className="border-t py-10"
          icon={<PiStackBold />}
          title={t("status.tasks.disconnected_title")}
          description={t("status.tasks.disconnected_description")}
        />
      </Card>
    );
  }

  const pending = tasks?.pending ?? [];
  const finished = tasks?.finished ?? [];
  const rows =
    filter === "pending"
      ? pending
      : filter === "finished"
        ? finished
        : [...pending, ...finished];
  const filters: [TaskFilter, number][] = [
    ["all", pending.length + finished.length],
    ["pending", pending.length],
    ["finished", finished.length],
  ];

  return (
    <Card
      title={t("status.tasks.title")}
      description={t("status.tasks.description")}
    >
      <div
        role="group"
        aria-label={t("status.tasks.filter")}
        className="flex flex-wrap gap-1.5 px-4 pb-3"
      >
        {filters.map(([key, count]) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
            className={cn(
              "h-6 rounded-full border px-2.5 text-xs font-medium inline-flex items-center gap-1.5 cursor-pointer outline-none focus-visible:ring-3 focus-visible:ring-ring",
              filter === key
                ? "bg-secondary border-transparent text-secondary-foreground"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            {t(`status.tasks.filters.${key}`)}
            <span className="tabular-nums opacity-70">{count}</span>
          </button>
        ))}
      </div>
      {tasks?.errors.map((error) => (
        <div
          key={error}
          role="alert"
          className="border-t px-4 py-2 text-xs text-destructive"
        >
          {t("status.tasks.error", { error })}
        </div>
      ))}
      {!tasks ? (
        <Loading />
      ) : rows.length === 0 ? (
        <div className="border-t px-4 py-8 text-center text-sm text-muted-foreground">
          {t(`status.tasks.empty.${filter}`)}
        </div>
      ) : (
        <>
          <ul>
            {rows.map((task, idx) => (
              <TaskRow key={idx} task={task} now={now} />
            ))}
          </ul>
          <div className="border-t bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
            {t("status.tasks.footer", { count: rows.length })}
          </div>
        </>
      )}
    </Card>
  );
}

function TaskRow({ task, now }: { task: StatusTask; now: number }) {
  const { t } = useTranslation();
  const when = task.at ? dayjs(task.at).from(dayjs(now)) : null;

  return (
    <li data-status={task.status} className="border-t px-4 py-3 space-y-1">
      <div className="flex items-start justify-between gap-3">
        <div className="font-medium min-w-0 break-words">{task.title}</div>
        <Badge variant="secondary" className="gap-1.5 pl-1.5 shrink-0">
          {task.status === "RUNNING" ? (
            <Spinner className="size-3" />
          ) : (
            <span
              className={cn("size-1.5 rounded-full", {
                "bg-success": task.status === "SUCCESS",
                "bg-destructive": task.status === "FAILURE",
                "bg-muted-foreground/60":
                  task.status === "QUEUED" || task.status === "SCHEDULED",
              })}
            />
          )}
          {t(`status.task_status.${task.status}`)}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 items-center text-xs text-muted-foreground empty:hidden">
        {task.source && <span>{task.source}</span>}
        {when && (
          <span className="inline-flex items-center gap-1">
            <PiClockBold />
            {task.status === "RUNNING"
              ? t("status.tasks.started", { when })
              : when}
          </span>
        )}
        {task.duration != null && (
          <span className="inline-flex items-center gap-1">
            <PiPlayCircleBold />
            {formatSeconds(task.duration)}
          </span>
        )}
      </div>
      {task.error_message && task.status === "FAILURE" && (
        <div className="text-xs text-destructive break-words">
          {task.error_message}
        </div>
      )}
    </li>
  );
}

function RecurringTasks({ tasks, now }: { tasks?: StatusTasks; now: number }) {
  const { t } = useTranslation();

  // Without a task backend and without registered tasks there is
  // nothing to say; the card above explains.
  if (tasks && !tasks.connected && tasks.recurring.length === 0) {
    return null;
  }

  return (
    <Card
      title={t("status.recurring.title")}
      description={t("status.recurring.description")}
    >
      {!tasks ? (
        <Loading />
      ) : tasks.recurring.length === 0 ? (
        <div className="border-t px-4 py-8 text-center text-sm text-muted-foreground">
          {t("status.recurring.empty")}
        </div>
      ) : (
        <ul>
          {tasks.recurring.map((task, idx) => (
            <RecurringRow key={task.key ?? idx} task={task} now={now} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function RecurringRow({ task, now }: { task: RecurringTask; now: number }) {
  const { t } = useTranslation();
  const running = task.last_status === "RUNNING";
  const failed = task.last_status === "FAILURE";
  const last = task.last_run_at
    ? dayjs(task.last_run_at).from(dayjs(now))
    : null;

  return (
    <li
      data-overdue={task.overdue || undefined}
      className="border-t px-4 py-3 space-y-1"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="font-medium break-words">{task.title}</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 items-center text-xs text-muted-foreground empty:hidden">
            {task.source && <span>{task.source}</span>}
            {task.schedule && (
              <span className="inline-flex items-center gap-1">
                <PiRepeatBold />
                {task.schedule}
              </span>
            )}
          </div>
        </div>
        <div className="text-right shrink-0 space-y-1">
          {task.next_run_at && (
            <div className={cn("font-medium", task.overdue && "text-warning")}>
              {task.overdue
                ? t("status.recurring.due", {
                    when: dayjs(task.next_run_at).from(dayjs(now)),
                  })
                : t("status.recurring.next", {
                    when: dayjs(task.next_run_at).from(dayjs(now)),
                  })}
            </div>
          )}
          <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            {running ? (
              <>
                <Spinner className="size-3" />
                {t("status.recurring.running")}
              </>
            ) : last ? (
              <>
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    failed ? "bg-destructive" : "bg-success",
                  )}
                />
                {failed
                  ? t("status.recurring.failed", { when: last })
                  : t("status.recurring.succeeded", { when: last })}
              </>
            ) : (
              t("status.recurring.never")
            )}
          </div>
        </div>
      </div>
      {task.error_message && (failed || !last) && (
        <div className="text-xs text-destructive break-words">
          {task.error_message}
        </div>
      )}
    </li>
  );
}
