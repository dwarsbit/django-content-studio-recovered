import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useDiscover } from "@/hooks/use-discover";
import { useHttp } from "@/hooks/use-http";
import { getDownloadFilename, saveFile } from "@/lib/download";
import type { DateTimeString } from "@/types";

// How often the list is asked for while a backup is queued or running.
export const BACKUPS_RUNNING_INTERVAL = 3_000;

export type BackupStatus = "queued" | "running" | "done" | "failed";
export type BackupTrigger =
  "scheduled" | "manual" | "command" | "before_restore";

export interface Backup {
  id: number;
  database: string;
  status: BackupStatus;
  trigger: BackupTrigger;
  // The file's name in the backup storage, and its last part.
  file: string;
  name: string;
  // Bytes.
  size: number | null;
  error: string | null;
  // Models left out because their table is not in the database.
  skipped: string[];
  created_by: string | null;
  created_at: DateTimeString;
  started_at: DateTimeString | null;
  finished_at: DateTimeString | null;
  // Seconds.
  duration: number | null;
}

export interface Backups {
  backups: Backup[];
  // The schedule in words, or null when backups are not scheduled.
  schedule: string | null;
  next_run_at: DateTimeString | null;
  // Backups kept per database; null keeps them all.
  keep: number | null;
  databases: string[];
  // The backup storage's class, or null when it is not configured.
  storage: string | null;
  folder: string;
  // The latest restores, newest first.
  restores?: Restore[];
  restore?: RestoreInfo;
}

export type RestoreStatus =
  "pending" | "queued" | "running" | "done" | "failed";

export interface Restore {
  id: number;
  database: string;
  status: RestoreStatus;
  source: "backup" | "upload";
  backup: number | null;
  // The backup's file name, or the uploaded file's.
  name: string;
  size: number | null;
  rows: number | null;
  error: string | null;
  // The file name of the backup made just before.
  safety_backup: string | null;
  created_by: string | null;
  created_at: DateTimeString;
  started_at: DateTimeString | null;
  finished_at: DateTimeString | null;
  duration: number | null;
}

export interface RestoreInfo {
  // Whether the signed-in user may restore on this page.
  enabled: boolean;
  // The databases a file can be restored into, with the name to type.
  databases: { alias: string; name: string }[];
  // Bytes; null has no limit.
  max_upload_size: number | null;
  // The file names a restore takes: ".json", ".json.gz", …
  suffixes: string[];
  password_required: boolean;
}

/** What a file would load, as the restore dialog shows it. */
export interface RestorePreview {
  database: string;
  // The name to type to confirm.
  database_name: string;
  // Whether the file came with a manifest (a Content Studio backup).
  manifest: boolean;
  created_at: DateTimeString | null;
  content_studio: string | null;
  django: string | null;
  engine: string | null;
  rows: number;
  models: { label: string; count: number }[];
  // Rows left out, and references matched by name (dumpdata files).
  skipped: number;
  remapped: number;
  unknown_models: string[];
  migrations: {
    checked: boolean;
    match: boolean;
    applied?: number;
    missing: string[];
    extra: string[];
  };
}

/** Whether the signed-in user has the Backups page. */
export function useBackupsEnabled() {
  const { data: discover } = useDiscover();

  return discover?.backups?.enabled === true;
}

const ACTIVE = new Set(["queued", "running"]);

/** Whether a backup is queued or running. */
export function isBackingUp(data: Backups | undefined) {
  return data?.backups.some((backup) => ACTIVE.has(backup.status)) ?? false;
}

/** The restore that is queued or running, if any. */
export function activeRestore(data: Backups | undefined) {
  return data?.restores?.find((restore) => ACTIVE.has(restore.status));
}

function isBusy(data: Backups | undefined) {
  return isBackingUp(data) || activeRestore(data) !== undefined;
}

export function useBackups() {
  const http = useHttp();

  return useQuery({
    retry: false,
    queryKey: ["backups"],
    refetchInterval: (query) =>
      isBusy(query.state.data) ? BACKUPS_RUNNING_INTERVAL : false,
    async queryFn() {
      const { data } = await http.get<Backups>("/backups");

      return data;
    },
  });
}

/** Back up every database now. */
export function useBackUpNow() {
  const http = useHttp();
  const queryClient = useQueryClient();

  return useMutation({
    async mutationFn() {
      const { data } = await http.post<{ backups: Backup[] }>("/backups");

      return data;
    },
    onSettled() {
      void queryClient.invalidateQueries({ queryKey: ["backups"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
  });
}

/** Save a backup's file. */
export function useDownloadBackup() {
  const http = useHttp();

  return useMutation({
    async mutationFn(backup: Backup) {
      const response = await http.get<Blob>(`/backups/${backup.id}/download`, {
        responseType: "blob",
      });
      const headers = (response.headers ?? {}) as Record<string, unknown>;
      const disposition = headers["content-disposition"];

      saveFile(
        response.data,
        getDownloadFilename(
          typeof disposition === "string" ? disposition : null,
          backup.name || `backup-${backup.id}.json.gz`,
        ),
      );
    },
  });
}

/** What restoring a listed backup would load. */
export function useRestorePreview(backup: Backup | null) {
  const http = useHttp();

  return useQuery({
    retry: false,
    enabled: backup !== null,
    gcTime: 0,
    queryKey: ["backups", backup?.id, "inspect"],
    async queryFn() {
      const { data } = await http.get<{ preview: RestorePreview }>(
        `/backups/${backup?.id}/inspect`,
      );

      return data.preview;
    },
  });
}

/** Upload a file to restore; it comes back with what it holds. */
export function useUploadRestoreFile() {
  const http = useHttp();

  return useMutation({
    async mutationFn({
      file,
      database,
      onProgress,
    }: {
      file: File;
      database?: string;
      onProgress?: (fraction: number) => void;
    }) {
      const body = new FormData();

      body.append("file", file);

      if (database) {
        body.append("database", database);
      }

      const { data } = await http.post<{
        upload: Restore;
        preview: RestorePreview;
      }>("/backups/uploads", body, {
        onUploadProgress(event) {
          if (event.total) {
            onProgress?.(event.loaded / event.total);
          }
        },
      });

      return data;
    },
  });
}

/** Delete an upload that is not restored. */
export function useCancelUpload() {
  const http = useHttp();

  return useMutation({
    async mutationFn(id: number) {
      await http.delete(`/backups/uploads/${id}`);
    },
  });
}

export interface StartRestore {
  backup?: number;
  upload?: number;
  confirm: string;
  password: string;
  safety_backup: boolean;
  ignore_migrations: boolean;
}

/** Start a restore of a listed backup or an upload. */
export function useStartRestore() {
  const http = useHttp();
  const queryClient = useQueryClient();

  return useMutation({
    async mutationFn(body: StartRestore) {
      const { data } = await http.post<{ restore: Restore }>(
        "/backups/restore",
        body,
      );

      return data.restore;
    },
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: ["backups"] });
    },
  });
}
