import { useMutation } from "@tanstack/react-query";

import { useHttp } from "@/hooks/use-http";
import { getDownloadFilename, saveFile } from "@/lib/download";
import type { ImportFormat, ImportJob, ImportResult } from "@/types";

// How often a background import's progress is fetched.
const POLL_INTERVAL = 1000;

export type ImportResponse =
  // Imported (or checked) in the request.
  | { result: ImportResult; job?: undefined }
  // Running as a task: follow it with waitForJob.
  | { job: ImportJob; result?: undefined };

export type ImportRequest =
  | { file: File; preview: boolean; skipErrors?: boolean }
  // The import that follows a background preview, on its stored file.
  | { job: string; preview?: false; skipErrors?: boolean };

/** Check or import a file into a model. */
export function useImport(modelLabel: string) {
  const http = useHttp();

  return useMutation({
    async mutationFn(request: ImportRequest): Promise<ImportResponse> {
      const data = new FormData();

      if ("file" in request) {
        data.append("file", request.file);
      } else {
        data.append("job", request.job);
      }

      data.append("preview", request.preview ? "true" : "false");
      data.append("skip_errors", request.skipErrors ? "true" : "false");

      const response = await http.post<ImportResponse>(
        `/content/${modelLabel}/import`,
        data,
      );

      return response.data;
    },
  });
}

/**
 * Follow a background import until it is done or failed, reporting its
 * progress on the way.
 */
export async function waitForJob(
  http: ReturnType<typeof useHttp>,
  modelLabel: string,
  job: ImportJob,
  onProgress?: (job: ImportJob) => void,
  signal?: AbortSignal,
): Promise<ImportJob> {
  let current = job;

  while (current.status === "queued" || current.status === "running") {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL));

    if (signal?.aborted) {
      return current;
    }

    const { data } = await http.get<{ job: ImportJob }>(
      `/content/${modelLabel}/import/${current.id}`,
    );

    current = data.job;
    onProgress?.(current);
  }

  return current;
}

/** Download the import template, or the list as an import reads it. */
export function useImportDownload(modelLabel: string) {
  const http = useHttp();

  return useMutation({
    async mutationFn(request: {
      format: ImportFormat;
      template?: boolean;
      params?: Record<string, string | null | undefined>;
    }) {
      const response = await http.get<Blob>(`/content/${modelLabel}/export`, {
        params: {
          ...(request.template ? {} : request.params),
          export_mode: request.template ? "template" : "import",
          export_format: request.format,
        },
        responseType: "blob",
      });
      const headers = (response.headers ?? {}) as Record<string, unknown>;
      const disposition = headers["content-disposition"];

      saveFile(
        response.data,
        getDownloadFilename(
          typeof disposition === "string" ? disposition : null,
          `${modelLabel.split(".").at(-1)}.${request.format}`,
        ),
      );
    },
  });
}
