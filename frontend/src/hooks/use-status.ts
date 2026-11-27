import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useDiscover } from "@/hooks/use-discover";
import { useHttp } from "@/hooks/use-http";
import type { DateTimeString } from "@/types";

// How often the user menu asks whether something is wrong.
export const STATUS_SUMMARY_INTERVAL = 5 * 60_000;
// How often the status page asks for the tasks, while it is open.
export const STATUS_TASKS_INTERVAL = 10_000;

export type ServiceStatus = "ok" | "degraded" | "down" | "unknown";

export interface StatusService {
  key: string;
  label: string;
  // The heading the service is listed under: its app.
  group: string;
  // A Phosphor icon class.
  icon: string | null;
  // Where the service's name links to: a path in the admin, or an
  // http(s) address (a new tab).
  url?: string | null;
  status: ServiceStatus;
  detail: string;
  message: string;
  // Milliseconds the check took.
  duration: number;
}

export interface SystemStatus {
  checked_at: DateTimeString;
  // The worst of the services: ok, degraded or down.
  status: ServiceStatus;
  services: StatusService[];
}

export type TaskRunStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "FAILURE";

export interface StatusTask {
  key: string | null;
  title: string;
  source: string;
  status: TaskRunStatus | "SCHEDULED";
  // When it started (running) or finished.
  at: DateTimeString | null;
  // Seconds.
  duration: number | null;
  error_message: string | null;
}

export interface RecurringTask {
  key: string | null;
  title: string;
  source: string;
  schedule: string;
  next_run_at: DateTimeString | null;
  last_run_at: DateTimeString | null;
  last_status: TaskRunStatus | null;
  error_message: string | null;
  // Past its next run without having started.
  overdue: boolean;
}

export interface StatusTasks {
  // Whether a task backend reports its tasks.
  connected: boolean;
  pending: StatusTask[];
  finished: StatusTask[];
  recurring: RecurringTask[];
  counts: { pending: number; failed: number };
  // Task backends that could not be read.
  errors: string[];
}

export interface RecentError {
  id: number;
  // The first line of the error.
  title: string;
  // The logger that reported it.
  logger: string;
  // How often it happened while the notification was unread.
  count: number;
  first_seen: DateTimeString;
  last_seen: DateTimeString;
  read: boolean;
}

export interface RecentErrors {
  // Error reports by email with the notifications app: otherwise there
  // is nothing to show.
  enabled: boolean;
  errors: RecentError[];
}

/** Whether the signed-in user has the status page. */
export function useStatusEnabled() {
  const { data: discover } = useDiscover();

  return discover?.status?.enabled === true;
}

/** The services, as last checked (at most a minute ago). */
export function useSystemStatus() {
  const http = useHttp();

  return useQuery({
    retry: false,
    queryKey: ["status", "services"],
    async queryFn() {
      const { data } = await http.get<SystemStatus>("/status");

      return data;
    },
  });
}

/** Check the services again, now. */
export function useRefreshStatus() {
  const http = useHttp();
  const queryClient = useQueryClient();

  return useMutation({
    async mutationFn() {
      const { data } = await http.post<SystemStatus>("/status/refresh");

      return data;
    },
    onSuccess(data) {
      queryClient.setQueryData(["status", "services"], data);
      queryClient.setQueryData(["status", "summary"], {
        status: data.status,
        checked_at: data.checked_at,
      });
      void queryClient.invalidateQueries({ queryKey: ["status", "tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["status", "errors"] });
    },
  });
}

/** The viewer's latest error reports, for the Recent errors card. */
export function useRecentErrors() {
  const http = useHttp();

  return useQuery({
    retry: false,
    queryKey: ["status", "errors"],
    async queryFn() {
      const { data } = await http.get<RecentErrors>("/status/errors");

      return data;
    },
  });
}

export function useStatusTasks() {
  const http = useHttp();

  return useQuery({
    retry: false,
    queryKey: ["status", "tasks"],
    refetchInterval: STATUS_TASKS_INTERVAL,
    refetchIntervalInBackground: false,
    async queryFn() {
      const { data } = await http.get<StatusTasks>("/status/tasks");

      return data;
    },
  });
}

/** The overall status, for the dot on the user menu. */
export function useStatusSummary() {
  const http = useHttp();
  const enabled = useStatusEnabled();

  return useQuery({
    enabled,
    retry: false,
    queryKey: ["status", "summary"],
    refetchInterval: STATUS_SUMMARY_INTERVAL,
    refetchIntervalInBackground: false,
    async queryFn() {
      const { data } = await http.get<{
        status: ServiceStatus;
        checked_at: DateTimeString;
      }>("/status/summary");

      return data;
    },
  });
}
