import dayjs from "dayjs";
import { type FormEvent, useId, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import {
  PiCaretRightBold,
  PiCheckCircleBold,
  PiInfoBold,
  PiUploadSimpleBold,
  PiWarningBold,
  PiWarningCircleBold,
} from "react-icons/pi";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import {
  type Backup,
  type RestoreInfo,
  type RestorePreview,
  useCancelUpload,
  useRestorePreview,
  useStartRestore,
  useUploadRestoreFile,
} from "@/hooks/use-backups";
import { formatNumber } from "@/lib/format-number";
import { cn, getErrorMessage } from "@/lib/utils";

import { formatBytes } from "./format";

/** What is restored: a listed backup, or a file the user uploads. */
export type RestoreSource =
  { kind: "backup"; backup: Backup } | { kind: "file" };

type Upload = { id: number; name: string; size: number | null };

type FieldErrors = Partial<
  Record<"confirm" | "password" | "ignore_migrations" | "detail", string>
>;

/**
 * Restore a listed backup or an uploaded file: see what it holds and how
 * its migrations compare, back up the current data first, and confirm
 * with the database's name and your password.
 */
export function RestoreDialog({
  source,
  info,
  onClose,
}: {
  // null when closed.
  source: RestoreSource | null;
  info: RestoreInfo;
  onClose(): void;
}) {
  const { t } = useTranslation();
  const [upload, setUpload] = useState<Upload | null>(null);
  const [uploadPreview, setUploadPreview] = useState<RestorePreview | null>(
    null,
  );
  const cancelUpload = useCancelUpload();
  const backup = source?.kind === "backup" ? source.backup : null;
  const backupPreview = useRestorePreview(backup);
  const preview = backup ? backupPreview.data : uploadPreview;

  function close() {
    if (upload) {
      // Not restored: the server deletes it now rather than in a day.
      cancelUpload.mutate(upload.id);
    }

    setUpload(null);
    setUploadPreview(null);
    onClose();
  }

  function started() {
    setUpload(null);
    setUploadPreview(null);
    onClose();
  }

  const title = backup
    ? t("backups.restore.title_backup")
    : preview
      ? t("backups.restore.title_file_preview")
      : t("backups.restore.title_file");

  return (
    <Dialog open={source !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-xl max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {preview
              ? backup
                ? t("backups.restore.description_backup", {
                    database: preview.database_name,
                    when: dayjs(backup.finished_at ?? backup.created_at).format(
                      "D MMM YYYY, HH:mm",
                    ),
                  })
                : t("backups.restore.description_file", {
                    database: preview.database_name,
                    name: upload?.name,
                  })
              : backup
                ? t("backups.restore.reading")
                : t("backups.restore.description_pick")}
          </DialogDescription>
        </DialogHeader>

        {backup ? (
          backupPreview.isError ? (
            <Alert variant="destructive">
              <PiWarningCircleBold />
              <AlertDescription>
                {getErrorMessage(backupPreview.error)}
              </AlertDescription>
            </Alert>
          ) : !preview ? (
            <div className="flex justify-center py-10">
              <Spinner className="size-5" />
            </div>
          ) : null
        ) : (
          !preview && (
            <FilePicker
              info={info}
              onUploaded={(next, nextPreview) => {
                setUpload(next);
                setUploadPreview(nextPreview);
              }}
            />
          )
        )}

        {preview && source !== null && (
          <ConfirmForm
            // A new file starts a new form.
            key={upload?.id ?? `backup-${backup?.id}`}
            preview={preview}
            backup={backup}
            upload={upload}
            info={info}
            onCancel={close}
            onStarted={started}
          />
        )}

        {!preview && (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close}>
              {t("backups.restore.cancel")}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function hasSuffix(name: string, suffixes: string[]) {
  const lower = name.toLowerCase();
  return suffixes.some((suffix) => lower.endsWith(suffix));
}

function FilePicker({
  info,
  onUploaded,
}: {
  info: RestoreInfo;
  onUploaded(upload: Upload, preview: RestorePreview): void;
}) {
  const { t } = useTranslation();
  const uploadFile = useUploadRestoreFile();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [database, setDatabase] = useState(info.databases[0]?.alias ?? "");
  const selectId = useId();

  async function send(next: File) {
    setError(null);

    if (!hasSuffix(next.name, info.suffixes)) {
      setError(
        t("backups.restore.wrong_type", { suffixes: info.suffixes.join(", ") }),
      );
      return;
    }

    if (info.max_upload_size !== null && next.size > info.max_upload_size) {
      setError(
        t("backups.restore.too_large", {
          size: formatBytes(info.max_upload_size),
        }),
      );
      return;
    }

    setFile(next);
    setProgress(0);

    try {
      const data = await uploadFile.mutateAsync({
        file: next,
        database,
        onProgress: setProgress,
      });

      onUploaded(
        { id: data.upload.id, name: data.upload.name, size: data.upload.size },
        data.preview,
      );
    } catch (e) {
      setFile(null);
      setError(fileError(e));
    }
  }

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    open: pick,
  } = useDropzone({
    multiple: false,
    noClick: true,
    noKeyboard: true,
    disabled: file !== null,
    onDropAccepted: (files) => files[0] && void send(files[0]),
  });

  const formats =
    info.max_upload_size !== null
      ? t("backups.restore.formats", {
          suffixes: info.suffixes.join(", "),
          size: formatBytes(info.max_upload_size),
        })
      : t("backups.restore.formats_unlimited", {
          suffixes: info.suffixes.join(", "),
        });

  return (
    <div className="min-w-0 space-y-4">
      {info.databases.length > 1 && !file && (
        <div className="space-y-1.5">
          <Label htmlFor={selectId}>{t("backups.restore.database")}</Label>
          <select
            id={selectId}
            value={database}
            onChange={(event) => setDatabase(event.target.value)}
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring"
          >
            {info.databases.map((option) => (
              <option key={option.alias} value={option.alias}>
                {option.alias === option.name
                  ? option.alias
                  : `${option.alias} (${option.name})`}
              </option>
            ))}
          </select>
        </div>
      )}
      {file ? (
        <div className="space-y-2 rounded-md border px-3 py-2.5">
          <div className="flex items-center gap-2 text-sm">
            <span className="flex-1 min-w-0 font-mono break-all">
              {file.name}
            </span>
            <span className="text-xs text-muted-foreground tabular-nums shrink-0">
              {progress < 1
                ? `${formatBytes(file.size * progress)} / ${formatBytes(file.size)}`
                : t("backups.restore.checking")}
            </span>
          </div>
          <div
            role="progressbar"
            aria-label={t("backups.restore.uploading")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress * 100)}
            className="h-1.5 rounded-full bg-muted overflow-hidden"
          >
            <div
              className="h-full bg-primary transition-[width]"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <div
          {...getRootProps({
            className: cn(
              "flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-8 text-center",
              {
                "border-2 border-ring ring-3 ring-ring/20": isDragActive,
                "border-destructive": error,
              },
            ),
          })}
        >
          <input {...getInputProps()} data-testid="restore-file-input" />
          <PiUploadSimpleBold className="size-6 text-muted-foreground" />
          <div className="space-y-1">
            <Button type="button" variant="outline" size="sm" onClick={pick}>
              {t("backups.restore.choose")}
            </Button>
            <p className="text-sm text-muted-foreground">
              {isDragActive ? t("backups.restore.drop") : formats}
            </p>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive break-words">
          {error}
        </p>
      )}
    </div>
  );
}

function fileError(e: unknown): string {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  const field = (data as { file?: unknown; database?: unknown } | null) ?? {};

  for (const value of [field.file, field.database]) {
    if (Array.isArray(value) && typeof value[0] === "string") {
      return value[0];
    }
  }

  return getErrorMessage(e);
}

function firstError(value: unknown): string | undefined {
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }

  return typeof value === "string" ? value : undefined;
}

function ConfirmForm({
  preview,
  backup,
  upload,
  info,
  onCancel,
  onStarted,
}: {
  preview: RestorePreview;
  backup: Backup | null;
  upload: Upload | null;
  info: RestoreInfo;
  onCancel(): void;
  onStarted(): void;
}) {
  const { t, i18n } = useTranslation();
  const start = useStartRestore();
  const [safety, setSafety] = useState(true);
  const [anyway, setAnyway] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const ids = {
    safety: useId(),
    anyway: useId(),
    confirm: useId(),
    password: useId(),
  };
  const number = (value: number) =>
    formatNumber(value, { format: "full", locale: i18n.language });
  const { migrations } = preview;
  const blocked = preview.unknown_models.length > 0;
  const needsAnyway = !migrations.match;
  const ready =
    !blocked &&
    confirm.trim() === preview.database_name &&
    (!info.password_required || password !== "") &&
    (!needsAnyway || anyway);

  // A change clears the errors of the last try.
  function edit<T>(set: (value: T) => void) {
    return (value: T) => {
      setErrors({});
      set(value);
    };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();

    if (!ready) {
      return;
    }

    try {
      await start.mutateAsync({
        ...(backup ? { backup: backup.id } : { upload: upload?.id }),
        confirm: confirm.trim(),
        password,
        safety_backup: safety,
        ignore_migrations: needsAnyway && anyway,
      });
      toast.success(t("backups.restore.started"));
      onStarted();
    } catch (e) {
      const data = (e as { response?: { data?: Record<string, unknown> } })
        ?.response?.data;

      if (data && !Array.isArray(data) && typeof data === "object") {
        const next: FieldErrors = {
          confirm: firstError(data.confirm),
          password: firstError(data.password),
          ignore_migrations: firstError(data.ignore_migrations),
          detail: firstError(data.detail),
        };

        if (Object.values(next).some(Boolean)) {
          setErrors(next);
          return;
        }
      }

      setErrors({ detail: getErrorMessage(e) });
    }
  }

  const shown = preview.models.slice(0, 5);
  const rest = preview.models.slice(5);

  return (
    <form className="min-w-0 space-y-4" onSubmit={(e) => void submit(e)}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 rounded-md border bg-muted px-3.5 py-3 text-sm">
        <Fact label={t("backups.restore.made")}>
          {preview.created_at
            ? `${dayjs(preview.created_at).format("D MMM YYYY, HH:mm")} · ${dayjs(preview.created_at).fromNow()}`
            : t("backups.restore.made_unknown")}
        </Fact>
        <Fact label={t("backups.restore.size")}>
          {formatBytes((backup ? backup.size : upload?.size) ?? 0)}
        </Fact>
        {preview.content_studio && (
          <Fact label={t("backups.restore.made_with")}>
            {t("backups.restore.versions", {
              content_studio: preview.content_studio,
              django: preview.django ?? "?",
            })}
          </Fact>
        )}
        {preview.engine && (
          <Fact label={t("backups.restore.engine")}>{preview.engine}</Fact>
        )}
        {!preview.manifest && (
          <Fact label={t("backups.restore.file")}>
            {t("backups.restore.dumpdata")}
          </Fact>
        )}
      </dl>

      <details className="group rounded-md border text-sm">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-medium [&::-webkit-details-marker]:hidden">
          <PiCaretRightBold className="size-3 text-muted-foreground transition-transform group-open:rotate-90" />
          {t("backups.restore.rows_in_models", {
            rows: number(preview.rows),
            count: preview.models.length,
          })}
        </summary>
        <ul>
          {shown.map((model) => (
            <li
              key={model.label}
              className="flex justify-between gap-3 border-t px-3 py-1.5 text-xs"
            >
              <span className="font-mono break-all">{model.label}</span>
              <span className="tabular-nums">{number(model.count)}</span>
            </li>
          ))}
          {rest.length > 0 && (
            <li className="flex justify-between gap-3 border-t px-3 py-1.5 text-xs text-muted-foreground">
              <span>
                {t("backups.restore.more_models", { count: rest.length })}
              </span>
              <span className="tabular-nums">
                {number(rest.reduce((sum, model) => sum + model.count, 0))}
              </span>
            </li>
          )}
        </ul>
      </details>

      {(preview.skipped > 0 || preview.remapped > 0) && (
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <PiInfoBold className="size-3.5 shrink-0 mt-0.5" />
          <span>
            {[
              preview.skipped > 0 &&
                t("backups.restore.skipped", { count: preview.skipped }),
              preview.remapped > 0 &&
                t("backups.restore.remapped", { count: preview.remapped }),
            ]
              .filter(Boolean)
              .join(" ")}
          </span>
        </p>
      )}

      {blocked ? (
        <Alert variant="destructive">
          <PiWarningCircleBold />
          <AlertDescription>
            {t("backups.restore.unknown_models", {
              models: preview.unknown_models.slice(0, 10).join(", "),
            })}
          </AlertDescription>
        </Alert>
      ) : migrations.match ? (
        <Alert variant="success">
          <PiCheckCircleBold />
          <AlertTitle>{t("backups.restore.migrations_match")}</AlertTitle>
          <AlertDescription>
            {t("backups.restore.migrations_match_detail", {
              count: migrations.applied ?? 0,
            })}
          </AlertDescription>
        </Alert>
      ) : (
        <Alert variant="warning">
          <PiWarningBold />
          <AlertTitle>
            {migrations.checked
              ? t("backups.restore.migrations_differ")
              : t("backups.restore.no_manifest")}
          </AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              {migrations.checked
                ? t("backups.restore.migrations_differ_detail")
                : t("backups.restore.no_manifest_detail")}
            </p>
            {migrations.missing.length > 0 && (
              <p className="font-mono text-xs break-all">
                {t("backups.restore.only_in_file", {
                  list: migrations.missing.slice(0, 5).join(", "),
                })}
              </p>
            )}
            {migrations.extra.length > 0 && (
              <p className="font-mono text-xs break-all">
                {t("backups.restore.only_in_database", {
                  list: migrations.extra.slice(0, 5).join(", "),
                })}
              </p>
            )}
            <div className="flex items-center gap-2 text-foreground">
              <Checkbox
                id={ids.anyway}
                checked={anyway}
                onCheckedChange={(value) => edit(setAnyway)(value === true)}
                aria-invalid={!!errors.ignore_migrations}
              />
              <Label htmlFor={ids.anyway}>{t("backups.restore.anyway")}</Label>
            </div>
          </AlertDescription>
        </Alert>
      )}

      {!blocked && (
        <>
          <div className="flex items-start gap-2.5">
            <Checkbox
              id={ids.safety}
              checked={safety}
              onCheckedChange={(value) => setSafety(value === true)}
              className="mt-0.5"
            />
            <div className="grid gap-0.5">
              <Label htmlFor={ids.safety}>{t("backups.restore.safety")}</Label>
              <span className="text-xs text-muted-foreground">
                {safety
                  ? t("backups.restore.safety_hint")
                  : t("backups.restore.no_safety_hint")}
              </span>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={ids.confirm}>
              {t("backups.restore.confirm", { name: preview.database_name })}
            </Label>
            <Input
              id={ids.confirm}
              value={confirm}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={!!errors.confirm}
              onChange={(event) => edit(setConfirm)(event.target.value)}
            />
            {errors.confirm && (
              <p className="text-xs text-destructive">{errors.confirm}</p>
            )}
          </div>

          {info.password_required && (
            <div className="space-y-1.5">
              <Label htmlFor={ids.password}>
                {t("backups.restore.password")}
              </Label>
              <Input
                id={ids.password}
                type="password"
                value={password}
                autoComplete="current-password"
                aria-invalid={!!errors.password}
                onChange={(event) => edit(setPassword)(event.target.value)}
              />
              {errors.password && (
                <p className="text-xs text-destructive">{errors.password}</p>
              )}
            </div>
          )}

          <p className="text-xs text-muted-foreground">
            {upload
              ? `${t("backups.restore.logout_hint")} ${t("backups.restore.upload_deleted")}`
              : t("backups.restore.logout_hint")}
          </p>
        </>
      )}

      {(errors.detail || errors.ignore_migrations) && (
        <p role="alert" className="text-sm text-destructive break-words">
          {errors.detail ?? errors.ignore_migrations}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("backups.restore.cancel")}
        </Button>
        <Button
          type="submit"
          variant="destructive"
          disabled={!ready || start.isPending}
        >
          {start.isPending && <Spinner className="size-4" />}
          {t("backups.restore.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

function Fact({ label, children }: { label: string; children: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium break-words">{children}</dd>
    </div>
  );
}
