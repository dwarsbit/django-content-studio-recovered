import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
} from "@tanstack/react-query";

import { useDiscover } from "@/hooks/use-discover";
import { useHttp } from "@/hooks/use-http";
import { getDownloadFilename, saveFile } from "@/lib/download";
import type { DateTimeString, ExportFormat } from "@/types";

export type ChangeAction =
  | "created"
  | "updated"
  | "deleted"
  | "restored"
  | "reordered"
  | "published"
  | "unpublished";

export type SignInAction = "signed_in" | "sign_in_failed" | "signed_out";

export type AuditAction = ChangeAction | SignInAction;

export interface AuditUser {
  id: number | string;
  username: string;
  label: string;
}

/** A change made in the admin: an activity log entry. */
export interface AuditChange {
  id: string;
  kind: "change";
  entry_id: number;
  action: ChangeAction;
  time: DateTimeString;
  user: AuditUser | null;
  // "app_label.model".
  model: string;
  model_name: string;
  object_id: string;
  object_repr: string;
  // Whether the object still exists (trashed objects do).
  object_exists: boolean;
  // The change in words, such as "Changed Title and Body.".
  message: string;
  // Whether the history app kept a version, which then opens.
  has_version: boolean;
}

/** A sign-in, failed sign-in or sign-out. */
export interface AuditSignIn {
  id: string;
  kind: "sign_in";
  action: SignInAction;
  time: DateTimeString;
  user: AuditUser | null;
  // As typed, for failed sign-ins.
  username: string;
  // "password", "two_factor", "recovery_code", "link" or a login
  // backend's name.
  method: string;
  // Why a sign-in failed: "wrong_password", "not_allowed", "locked",
  // "wrong_code" or "wrong_recovery_code".
  reason: string;
  ip_address: string | null;
  // "Firefox on macOS".
  browser: string;
  user_agent: string;
}

export type AuditEntry = AuditChange | AuditSignIn;

export interface AuditLogOptions {
  models: { value: string; label: string }[];
  users: { value: string; label: string; username: string }[];
  actions: AuditAction[];
  export_formats: ExportFormat[];
  // Days entries are kept; null keeps them.
  keep_days: number | null;
  // Whether the history app keeps versions.
  history: boolean;
}

export interface AuditLogPage {
  entries: AuditEntry[];
  // The cursor of the next page; null at the end.
  next: string | null;
  limit: number;
  // The first page only.
  options?: AuditLogOptions;
}

/** The list's filters; undefined filters nothing. */
export interface AuditLogQuery {
  user?: string;
  model?: string;
  object?: string;
  action?: AuditAction;
  // Dates (YYYY-MM-DD, both included) or ISO date-times.
  since?: string;
  until?: string;
  q?: string;
}

export interface AuditVersion extends AuditChange {
  fields: string[];
  previous: Record<string, unknown>;
  data: Record<string, unknown>;
}

function params(query: AuditLogQuery) {
  return Object.fromEntries(
    Object.entries(query).filter(
      ([, value]) => value !== undefined && value !== "",
    ),
  );
}

export function useAuditLogEnabled() {
  const { data: discover } = useDiscover();

  return discover?.audit_log?.enabled === true;
}

/** The timeline, newest first, a page at a time. */
export function useAuditLog(query: AuditLogQuery = {}) {
  const http = useHttp();
  const enabled = useAuditLogEnabled();

  return useInfiniteQuery({
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
    queryKey: ["audit-log", query],
    async queryFn({ pageParam }) {
      const { data } = await http.get<AuditLogPage>("/audit-log", {
        params: { ...params(query), after: pageParam ?? undefined },
      });

      return data;
    },
    initialPageParam: null as string | null,
    getNextPageParam: (page: AuditLogPage) => page.next ?? undefined,
  });
}

/** The version the history app kept with a change. */
export function useAuditVersion(entryId: number | null) {
  const http = useHttp();

  return useQuery({
    enabled: entryId !== null,
    retry: false,
    queryKey: ["audit-log", "version", entryId],
    async queryFn() {
      const { data } = await http.get<AuditVersion>(
        `/audit-log/changes/${entryId}`,
      );

      return data;
    },
  });
}

/** Download the filtered timeline as a file. */
export function useAuditLogExport() {
  const http = useHttp();

  return useMutation({
    async mutationFn({
      format,
      query,
    }: {
      format: ExportFormat;
      query: AuditLogQuery;
    }) {
      const response = await http.get<Blob>("/audit-log/export", {
        params: { ...params(query), export_format: format },
        responseType: "blob",
      });
      const headers = (response.headers ?? {}) as Record<string, unknown>;
      const disposition = headers["content-disposition"];

      saveFile(
        response.data,
        getDownloadFilename(
          typeof disposition === "string" ? disposition : null,
          `audit-log.${format}`,
        ),
      );
    },
  });
}
