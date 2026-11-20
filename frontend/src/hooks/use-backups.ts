import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useDiscover } from "@/hooks/use-discover";
import { useHttp } from "@/hooks/use-http";
import { getDownloadFilename, saveFile } from "@/lib/download";
import type { DateTimeString } from "@/types";

// How often the list is asked for while a backup is queued or running.
export const BACKUPS_RUNNING_INTERVAL = 3_000;

export type BackupStatus = "queued" | "running" | "done" | "failed";
export type BackupTrigger = "scheduled" | "manual" | "command";

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
}

/** Whether the signed-in user has the Backups page. */
export function useBackupsEnabled() {
  const { data: discover } = useDiscover();

  return discover?.backups?.enabled === true;
}

function isBusy(data: Backups | undefined) {
  return (
    data?.backups.some(
      (backup) => backup.status === "queued" || backup.status === "running",
    ) ?? false
  );
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
