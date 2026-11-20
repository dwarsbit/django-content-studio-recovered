import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import {
  PiFileBold,
  PiUploadSimpleBold,
  PiWarningBold,
  PiWarningCircleBold,
} from "react-icons/pi";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { useHttp } from "@/hooks/use-http";
import {
  type ImportResponse,
  useImport,
  useImportDownload,
  waitForJob,
} from "@/hooks/use-import";
import { getDownloadErrorMessage } from "@/lib/download";
import { formatNumber } from "@/lib/format-number";
import { cn, getErrorMessage } from "@/lib/utils";
import type { ImportJob, ImportResult, Model } from "@/types";

const ACCEPT = {
  "text/csv": [".csv"],
  "application/json": [".json"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
};

type Step =
  | { name: "pick"; error?: string }
  | { name: "checking"; file: File; job?: ImportJob }
  | { name: "preview"; file: File; result: ImportResult; job?: string }
  | { name: "importing"; file: File; result: ImportResult; job?: ImportJob };

/**
 * Import a file into a model's list: pick a CSV, Excel or JSON file, see
 * what it would create, update and leave unchanged and which rows fail,
 * then import every row, or only the valid ones. Large files run in the
 * background; the import then reports its progress in a toast.
 */
export function ImportDialog({
  model,
  open,
  onOpenChange,
}: {
  model: Model;
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  const { t, i18n } = useTranslation();
  const http = useHttp();
  const queryClient = useQueryClient();
  const config = model.admin.list.import;
  const [step, setStep] = useState<Step>({ name: "pick" });
  const { mutateAsync: runImport } = useImport(model.label);
  const { mutateAsync: download } = useImportDownload(model.label);
  // Stops following a background check when the dialog closes.
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const number = (value: number) =>
    formatNumber(value, { format: "full", locale: i18n.language });

  function close() {
    abort.current?.abort();
    onOpenChange(false);
    setStep({ name: "pick" });
  }

  /** Closed by the editor: a checked file left unimported is removed. */
  function cancel() {
    if (step.name === "preview" && step.job) {
      void http
        .delete(`/content/${model.label}/import/${step.job}`)
        .catch(() => undefined);
    }

    close();
  }

  async function check(file: File) {
    abort.current?.abort();
    abort.current = new AbortController();
    setStep({ name: "checking", file });

    try {
      const response = await runImport({ file, preview: true });
      const signal = abort.current.signal;
      const result = await resultOf(
        response,
        (job) => {
          if (!signal.aborted) {
            setStep({ name: "checking", file, job });
          }
        },
        signal,
      );

      if (signal.aborted) {
        return;
      }

      setStep({ name: "preview", file, result, job: response.job?.id });
    } catch (e) {
      setStep({ name: "pick", error: fileError(e) });
    }
  }

  async function resultOf(
    response: ImportResponse,
    onProgress?: (job: ImportJob) => void,
    signal?: AbortSignal,
  ): Promise<ImportResult> {
    if (response.result) {
      return response.result;
    }

    const job = await waitForJob(
      http,
      model.label,
      response.job,
      onProgress,
      signal,
    );

    if (job.status === "failed" || !job.result) {
      throw new Error(job.error ?? t("import.failed"));
    }

    return job.result;
  }

  async function confirm(skipErrors: boolean) {
    if (step.name !== "preview") {
      return;
    }

    const { file, result, job } = step;

    setStep({ name: "importing", file, result });

    try {
      const response = await runImport(
        job ? { job, skipErrors } : { file, preview: false, skipErrors },
      );

      if (response.job) {
        // Runs in the background: the toast follows it from here.
        close();
        followInToast(response.job);
        return;
      }

      finish(response.result);
    } catch (e) {
      toast.error(getErrorMessage(e));
      setStep({ name: "preview", file, result, job });
    }
  }

  function followInToast(job: ImportJob) {
    const id = toast.loading(progressLabel(job));

    waitForJob(http, model.label, job, (current) =>
      toast.loading(progressLabel(current), { id }),
    )
      .then((done) => {
        if (done.status === "failed" || !done.result) {
          toast.error(done.error ?? t("import.failed"), { id });
          return;
        }

        report(done.result, id);
      })
      .catch((e) => toast.error(getErrorMessage(e), { id }));
  }

  function finish(result: ImportResult) {
    if (!result.applied) {
      // Rows failed since the check: nothing was saved; show them.
      if (step.name === "preview" || step.name === "importing") {
        setStep({ name: "preview", file: step.file, result });
      }
      toast.error(t("import.not_applied"));
      return;
    }

    close();
    report(result);
  }

  function report(result: ImportResult, id?: string | number) {
    void queryClient.invalidateQueries({
      queryKey: ["resources", model.label],
    });

    const parts = (
      [
        ["created", result.created],
        ["updated", result.updated],
        ["unchanged", result.unchanged],
        ["skipped", result.failed],
      ] as const
    )
      .filter(([, count]) => count > 0)
      .map(([key, count]) => t(`import.summary.${key}`, { count }));

    toast.success(t("import.done", { plural: model.verbose_name_plural }), {
      id,
      description: parts.join(" · "),
    });
  }

  function progressLabel(job: ImportJob) {
    return job.processed
      ? t("import.progress", {
          processed: number(job.processed),
          total: number(job.total),
        })
      : t("import.queued", { total: number(job.total) });
  }

  async function downloadTemplate(format: "csv" | "xlsx") {
    try {
      await download({ format, template: true });
    } catch (e) {
      toast.error(await getDownloadErrorMessage(e));
    }
  }

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    open: pick,
  } = useDropzone({
    accept: ACCEPT,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    disabled: step.name !== "pick" && step.name !== "preview",
    onDropAccepted: (files) => files[0] && void check(files[0]),
    onDropRejected: () =>
      setStep({ name: "pick", error: t("import.wrong_type") }),
  });

  if (!config) {
    return null;
  }

  const matchedOnPk = config.key.length === 1 && config.key[0] === "id";
  const keyLabels = config.key
    .map((name) => config.columns.find((c) => c.name === name)?.label ?? name)
    .join(", ");

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : cancel())}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {t("import.title", { plural: model.verbose_name_plural })}
          </DialogTitle>
          <DialogDescription>
            {matchedOnPk
              ? t("import.description_pk", {
                  name: model.verbose_name,
                })
              : t("import.description_key", {
                  key: keyLabels,
                  name: model.verbose_name,
                })}
          </DialogDescription>
        </DialogHeader>

        <div className="min-w-0 space-y-4">
          {step.name === "pick" ? (
            <>
              <div
                {...getRootProps({
                  className: cn(
                    "flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-8 text-center",
                    {
                      "border-2 border-ring ring-3 ring-ring/20": isDragActive,
                      "border-destructive": step.error,
                    },
                  ),
                })}
              >
                <input {...getInputProps()} data-testid="import-file-input" />
                <PiUploadSimpleBold className="size-6 text-muted-foreground" />
                <div className="space-y-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={pick}
                  >
                    {t("import.choose")}
                  </Button>
                  <p className="text-sm text-muted-foreground">
                    {isDragActive ? t("import.drop") : t("import.formats")}
                  </p>
                </div>
              </div>
              {step.error && (
                <p role="alert" className="text-sm text-destructive">
                  {step.error}
                </p>
              )}
              <Columns config={config} onTemplate={downloadTemplate} />
            </>
          ) : (
            <>
              <FileRow
                file={step.file}
                onReplace={step.name === "preview" ? pick : undefined}
                rootProps={getRootProps()}
                inputProps={getInputProps()}
              />
              {step.name === "checking" ? (
                <Progress
                  label={
                    step.job?.processed
                      ? t("import.checking_progress", {
                          processed: number(step.job.processed),
                          total: number(step.job.total),
                        })
                      : t("import.checking")
                  }
                  value={
                    step.job?.total
                      ? step.job.processed / step.job.total
                      : undefined
                  }
                />
              ) : (
                <Preview result={step.result} number={number} />
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={cancel}>
            {t("common.cancel")}
          </Button>
          {(step.name === "preview" || step.name === "importing") && (
            <ConfirmButton
              result={step.result}
              pending={step.name === "importing"}
              number={number}
              onConfirm={confirm}
            />
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function fileError(e: unknown): string {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  const file = (data as { file?: unknown } | null)?.file;

  if (Array.isArray(file) && typeof file[0] === "string") {
    return file[0];
  }

  if (typeof file === "string") {
    return file;
  }

  if (e instanceof Error && !(e as { response?: unknown }).response) {
    return e.message;
  }

  return getErrorMessage(e);
}

function Columns({
  config,
  onTemplate,
}: {
  config: NonNullable<Model["admin"]["list"]["import"]>;
  onTemplate(format: "csv" | "xlsx"): void;
}) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2 text-sm">
      <p className="text-muted-foreground">
        {t("import.columns")}{" "}
        {config.columns.map((column, index) => (
          <span key={column.name}>
            {index > 0 && ", "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs text-foreground">
              {column.name}
            </code>
            {column.lookup && (
              <span className="text-xs">
                {" "}
                ({t("import.by_lookup", { lookup: column.lookup })})
              </span>
            )}
            {column.required && <span aria-hidden> *</span>}
          </span>
        ))}
      </p>
      {config.template_formats.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-2 text-muted-foreground">
          {t("import.template")}
          {config.template_formats.map((format) => (
            <Button
              key={format}
              type="button"
              variant="link"
              size="sm"
              className="h-auto px-0"
              onClick={() => onTemplate(format)}
            >
              {t(`export.${format}`)}
            </Button>
          ))}
        </p>
      )}
    </div>
  );
}

function FileRow({
  file,
  onReplace,
  rootProps,
  inputProps,
}: {
  file: File;
  onReplace?: () => void;
  rootProps: object;
  inputProps: object;
}) {
  const { t } = useTranslation();

  return (
    <div
      {...rootProps}
      className="flex items-center gap-3 rounded-lg border bg-background p-2"
    >
      <input {...inputProps} />
      <div className="flex size-9 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground">
        <PiFileBold className="size-5" />
      </div>
      <span className="min-w-0 flex-1 truncate text-sm font-medium">
        {file.name}
      </span>
      {onReplace && (
        <Button type="button" variant="ghost" size="sm" onClick={onReplace}>
          {t("import.replace")}
        </Button>
      )}
    </div>
  );
}

function Progress({ label, value }: { label: string; value?: number }) {
  return (
    <div className="space-y-2 py-2">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner className="size-4" />
        {label}
      </div>
      {value !== undefined && (
        <div className="h-1 overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${Math.round(value * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

function Preview({
  result,
  number,
}: {
  result: ImportResult;
  number(value: number): string;
}) {
  const { t } = useTranslation();

  if (result.errors.length > 0) {
    return (
      <Alert variant="destructive">
        <PiWarningCircleBold />
        <AlertTitle>{t("import.cannot_import")}</AlertTitle>
        <AlertDescription>
          {result.errors.map((error) => (
            <p key={error}>{error}</p>
          ))}
        </AlertDescription>
      </Alert>
    );
  }

  const tiles = [
    { key: "created", value: result.created },
    { key: "updated", value: result.updated },
    { key: "unchanged", value: result.unchanged },
    { key: "failed", value: result.failed },
  ] as const;
  const hidden = result.failed - result.failures.length;

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {tiles.map((tile) => (
          <div
            key={tile.key}
            className={cn("rounded-lg border px-3 py-2", {
              "border-destructive/40 bg-destructive/5":
                tile.key === "failed" && tile.value > 0,
            })}
          >
            <dt className="text-xs text-muted-foreground">
              {t(`import.counts.${tile.key}`)}
            </dt>
            <dd
              className={cn("text-lg font-semibold tabular-nums", {
                "text-destructive": tile.key === "failed" && tile.value > 0,
                "text-muted-foreground": tile.value === 0,
              })}
            >
              {number(tile.value)}
            </dd>
          </div>
        ))}
      </dl>

      {result.ignored_columns.length > 0 && (
        <Alert variant="warning">
          <PiWarningBold />
          <AlertDescription>
            {t("import.ignored_columns", {
              count: result.ignored_columns.length,
              columns: result.ignored_columns.join(", "),
            })}
          </AlertDescription>
        </Alert>
      )}

      {result.failures.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{t("import.failing_rows")}</p>
          <ul className="max-h-56 divide-y overflow-y-auto rounded-lg border text-sm">
            {result.failures.map((failure) => (
              <li key={failure.row} className="flex gap-3 px-3 py-2">
                <span className="w-14 shrink-0 text-muted-foreground tabular-nums">
                  {t("import.row", { row: failure.row })}
                </span>
                <div className="min-w-0 space-y-0.5">
                  {failure.errors.map((error, index) => (
                    <p key={index} className="break-words">
                      {error.column && (
                        <span className="font-medium">{error.column}: </span>
                      )}
                      {error.messages.join(" ")}
                    </p>
                  ))}
                </div>
              </li>
            ))}
            {hidden > 0 && (
              <li className="px-3 py-2 text-muted-foreground">
                {t("import.more_rows", { count: hidden })}
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConfirmButton({
  result,
  pending,
  number,
  onConfirm,
}: {
  result: ImportResult;
  pending: boolean;
  number(value: number): string;
  onConfirm(skipErrors: boolean): void;
}) {
  const { t } = useTranslation();
  const valid = result.total - result.failed;
  const changes = result.created + result.updated;
  const disabled =
    pending || result.errors.length > 0 || valid === 0 || changes === 0;

  return (
    <Button disabled={disabled} onClick={() => onConfirm(result.failed > 0)}>
      {pending && <Spinner className="size-4" />}
      {result.errors.length > 0 || valid === 0
        ? t("import.nothing_valid")
        : changes === 0
          ? t("import.nothing_changes")
          : result.failed > 0
            ? t("import.import_valid", { count: valid, number: number(valid) })
            : t("import.import_all", { count: valid, number: number(valid) })}
    </Button>
  );
}
