import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiCalendarBlankBold, PiWarningBold } from "react-icons/pi";

import { Change } from "@/components/form-components/version-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { UserAvatar } from "@/components/ui/user-avatar";
import { useHttp } from "@/hooks/use-http";
import type { Model, ReviewDetails } from "@/types";

dayjs.extend(relativeTime);

function capfirst(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Review: the submitter's note and the changes, field by field, against
 * the live or last approved version; then request changes, or approve
 * it, which publishes or schedules exactly the version shown.
 */
export function ReviewDialog({
  open,
  onOpenChange,
  ...props
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  model: Model;
  name: string;
  // The object's API path.
  resourcePath: string;
  live: boolean;
  isPending: boolean;
  onRequestChanges(note: string): Promise<void>;
  onApprove(version: string, note: string): Promise<void>;
  onApproveAndSchedule(version: string, note: string): void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] grid-rows-[auto_minmax(0,1fr)_auto]">
        {open && <ReviewForm {...props} />}
      </DialogContent>
    </Dialog>
  );
}

function ReviewForm({
  model,
  name,
  resourcePath,
  live,
  isPending,
  onRequestChanges,
  onApprove,
  onApproveAndSchedule,
}: {
  model: Model;
  name: string;
  resourcePath: string;
  live: boolean;
  isPending: boolean;
  onRequestChanges(note: string): Promise<void>;
  onApprove(version: string, note: string): Promise<void>;
  onApproveAndSchedule(version: string, note: string): void;
}) {
  const { t, i18n } = useTranslation();
  const http = useHttp();
  const [note, setNote] = useState("");
  const [noteMissing, setNoteMissing] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["review", resourcePath],
    async queryFn() {
      const { data } = await http.get<ReviewDetails>(`${resourcePath}/review`);
      return data;
    },
  });
  const review = data?.review;
  const changes = data?.changes;
  const fields = (changes?.fields ?? []).filter((field) => model.fields[field]);
  const label = (field: string) =>
    capfirst(model.fields[field]?.verbose_name ?? field);
  const edited = (data?.changed_since_submitted ?? []).filter(
    (field) => model.fields[field],
  );

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("review.dialog.title")}</DialogTitle>
        <DialogDescription>
          {review?.submitted_by
            ? t("review.dialog.submitted_by", {
                name: review.submitted_by.name,
                object: name,
                when: dayjs(review.submitted_at).fromNow(),
              })
            : t("review.dialog.description", { object: name })}
        </DialogDescription>
      </DialogHeader>
      <div className="overflow-y-auto scrollbar -mx-6 px-6 space-y-5">
        {isLoading || !data ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : (
          <>
            {review?.note && (
              <div className="rounded-md bg-muted px-3 py-2.5 text-sm flex gap-2.5">
                {review.submitted_by && (
                  <UserAvatar
                    name={review.submitted_by.name}
                    initials={review.submitted_by.initials}
                    src={review.submitted_by.avatar}
                    className="shrink-0"
                  />
                )}
                <p
                  className="whitespace-pre-wrap break-words min-w-0"
                  data-testid="review-submitter-note"
                >
                  {review.note}
                </p>
              </div>
            )}
            {edited.length > 0 && (
              <div
                className="rounded-md border border-yellow-500/40 bg-yellow-500/10 px-3 py-2.5 text-sm flex gap-2"
                data-testid="review-edited"
              >
                <PiWarningBold className="shrink-0 mt-0.5 text-yellow-600" />
                <span>
                  {t("review.dialog.edited_since", {
                    fields: new Intl.ListFormat(i18n.language, {
                      type: "conjunction",
                    }).format(edited.map(label)),
                  })}
                </span>
              </div>
            )}
            <div>
              <div className="text-sm font-semibold mb-2">
                {changes?.base === null
                  ? t("review.dialog.new_content")
                  : t(
                      changes?.base === "live"
                        ? "review.dialog.changed_live"
                        : "review.dialog.changed_approved",
                      { count: fields.length },
                    )}
              </div>
              {changes?.base === null ? (
                <p className="text-sm text-muted-foreground">
                  {t("review.dialog.new_content_hint")}
                </p>
              ) : (
                <dl className="divide-y" data-testid="review-fields">
                  {fields.map((field) => (
                    <div key={field} className="py-3 first:pt-0">
                      <dt className="text-sm font-medium mb-1.5">
                        {label(field)}
                      </dt>
                      <dd className="min-w-0">
                        <Change
                          field={model.fields[field]}
                          before={changes?.before[field]}
                          after={changes?.after[field]}
                        />
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="review-decision-note">
                {t("review.dialog.note")}
              </Label>
              <Textarea
                id="review-decision-note"
                value={note}
                rows={3}
                maxLength={10000}
                aria-invalid={noteMissing || undefined}
                onChange={(event) => {
                  setNote(event.target.value);
                  setNoteMissing(false);
                }}
              />
              <p
                className={
                  noteMissing
                    ? "text-xs text-destructive"
                    : "text-xs text-muted-foreground"
                }
              >
                {t("review.dialog.note_hint")}
              </p>
            </div>
          </>
        )}
      </div>
      <DialogFooter className="sm:justify-between gap-2">
        <Button
          variant="outline"
          className="text-destructive"
          disabled={!data || isPending}
          data-testid="review-request-changes"
          onClick={() => {
            if (!note.trim()) {
              setNoteMissing(true);
              return;
            }

            onRequestChanges(note);
          }}
        >
          {t("review.request_changes")}
        </Button>
        <div className="flex flex-col-reverse sm:flex-row gap-2">
          {!live && (
            <Button
              variant="outline"
              disabled={!data || isPending}
              onClick={() => data && onApproveAndSchedule(data.version, note)}
            >
              <PiCalendarBlankBold />
              {t("review.approve_schedule")}
            </Button>
          )}
          <Button
            isLoading={isPending}
            disabled={!data}
            data-testid="review-approve"
            onClick={() => data && onApprove(data.version, note)}
          >
            {t("review.approve_publish")}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
