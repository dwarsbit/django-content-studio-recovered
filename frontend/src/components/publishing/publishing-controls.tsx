import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ReviewDialog } from "@/components/review/review-dialog";
import { SubmitDialog } from "@/components/review/submit-dialog";
import useConfirmDialog from "@/hooks/use-confirm-dialog";
import { useHttp } from "@/hooks/use-http";
import { getErrorMessage } from "@/lib/utils";
import type { Model, PublishingInfo, Resource, ReviewInfo } from "@/types";

import { CompareDialog } from "./compare-dialog";
import {
  type PublishingAction,
  PublishingContext,
  type PublishingControls,
  type ReviewAction,
} from "./publishing";
import { ScheduleDialog, UnpublishDateDialog } from "./schedule-dialog";

// The first message of a refused change: a field's (at, unpublish_at)
// or the request's.
function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;

  if (data && typeof data === "object" && !Array.isArray(data)) {
    for (const key of [
      "at",
      "unpublish_at",
      "note",
      "reviewer",
      "version",
      "non_field_errors",
    ]) {
      const messages = (data as Record<string, unknown>)[key];

      if (Array.isArray(messages) && messages.length) {
        return String(messages[0]);
      }
    }
  }

  return getErrorMessage(error) as string;
}

/**
 * Publishing for a saved object of a studio with publishing: publish
 * now, schedule, cancel the schedule, unpublish and the unpublish date.
 * Publishing saves the form's unsaved changes first, so what goes live
 * is what the editor sees.
 */
export function PublishingProvider({
  model,
  resource,
  resourcePath,
  isDirty,
  readOnly,
  save,
  onChanged,
  children,
}: {
  model: Model;
  resource?: Resource;
  resourcePath: string;
  isDirty: boolean;
  readOnly: boolean;
  // Saves the form; resolves whether it saved.
  save(): Promise<boolean>;
  // Shows the object's new state.
  onChanged(): Promise<void>;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const confirm = useConfirmDialog();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<
    "schedule" | "unpublish_at" | "compare" | "submit" | "review" | null
  >(null);
  // Approve and schedule: the version the reviewer approves, and their
  // note, while the Schedule dialog asks when.
  const [approving, setApproving] = useState<{
    version: string;
    note: string;
  } | null>(null);
  const config = model.admin.list.publishing;
  const info = resource?.__publishing__;

  const { mutateAsync, isPending } = useMutation({
    async mutationFn(
      data: { action: PublishingAction } & Record<string, unknown>,
    ) {
      const { data: result } = await http.post<PublishingInfo>(
        `${resourcePath}/${resource!.id}/publishing`,
        data,
      );
      return result;
    },
  });

  const review = useMutation({
    async mutationFn(data: { action: ReviewAction } & Record<string, unknown>) {
      const { data: result } = await http.post<{ review: ReviewInfo | null }>(
        `${resourcePath}/${resource!.id}/review`,
        data,
      );
      return result;
    },
  });

  // An editor without publishing hides any outer one's, such as the
  // article's from a category edited in a dialog on its page. The tree
  // keeps its shape either way, so the form is not remounted when the
  // object arrives.
  if (!config || !info || resource?.id == null) {
    return (
      <PublishingContext value={null}>
        {children}
        {null}
      </PublishingContext>
    );
  }

  const name = resource.__str__ || model.verbose_name;

  // Runs a change, saving unsaved changes first (unless saveFirst is
  // false); resolves whether it happened (a dialog stays open on a
  // refused one, which shows why).
  async function run(
    data: { action: PublishingAction } & Record<string, unknown>,
    success: string,
    saveFirst = true,
  ) {
    if (saveFirst && isDirty && !readOnly && !(await save())) {
      return false;
    }

    try {
      await mutateAsync(data);
    } catch (error: unknown) {
      toast.error(errorMessage(error));
      return false;
    }

    await onChanged();
    toast.success(success);
    return true;
  }

  // Runs a review action; submitting saves unsaved changes first, so
  // what is reviewed is what the editor sees.
  async function runReview(
    data: { action: ReviewAction } & Record<string, unknown>,
    success: string,
  ) {
    if (data.action === "submit" && isDirty && !readOnly && !(await save())) {
      return false;
    }

    try {
      await review.mutateAsync(data);
    } catch (error: unknown) {
      toast.error(errorMessage(error));
      return false;
    }

    await onChanged();
    // The review's notes are posted as comments.
    await queryClient.invalidateQueries({ queryKey: ["comments"] });
    await queryClient.invalidateQueries({ queryKey: ["review"] });
    toast.success(success);
    return true;
  }

  // On studios with pending_changes, saving a live object keeps the
  // changes unpublished until Publish changes.
  const holdsChanges = !!config.pending_changes && info.state === "published";
  const current =
    info.review && "id" in info.review ? (info.review as ReviewInfo) : null;
  const busy = isPending || review.isPending;

  const controls: PublishingControls = {
    info,
    unpublish: config.unpublish,
    canPublish: info.can_publish ?? config.can_publish,
    isPending: busy,
    hasChanges: holdsChanges && (!!info.has_pending || (isDirty && !readOnly)),
    canDiscard: !readOnly,
    async publishChanges() {
      await run(
        { action: "publish_changes" },
        t("publishing.toast.changes_published", { name }),
      );
    },
    async discardChanges() {
      const confirmed = await confirm({
        title: t("publishing.changes.discard_title"),
        description: t("publishing.changes.discard_description", { name }),
        okText: t("publishing.changes.discard"),
      });

      if (confirmed) {
        await run(
          { action: "discard_changes" },
          t("publishing.toast.changes_discarded", { name }),
          false,
        );
      }
    },
    openCompare() {
      setDialog("compare");
    },
    fieldLabel(name) {
      const label = model.fields[name]?.verbose_name ?? name;

      return label.charAt(0).toUpperCase() + label.slice(1);
    },
    async publishNow() {
      await run(
        { action: "publish" },
        t("publishing.toast.published", { name }),
      );
    },
    openSchedule() {
      setDialog("schedule");
    },
    async cancelSchedule() {
      const confirmed = await confirm({
        title: t("publishing.cancel_schedule.title"),
        description: t("publishing.cancel_schedule.description", { name }),
        okText: t("publishing.cancel_schedule.ok"),
      });

      if (confirmed) {
        await run(
          { action: "unpublish" },
          t("publishing.toast.unscheduled", { name }),
        );
      }
    },
    async unpublishNow() {
      const confirmed = await confirm({
        title: t("publishing.unpublish.title"),
        description: t("publishing.unpublish.description", { name }),
        okText: t("publishing.unpublish.ok"),
      });

      if (confirmed) {
        await run(
          { action: "unpublish" },
          t("publishing.toast.unpublished", { name }),
        );
      }
    },
    openUnpublishDate() {
      setDialog("unpublish_at");
    },
    review: config.review
      ? {
          required: config.review.required,
          current,
          canSubmit: !readOnly,
          comments: !!model.admin.comments,
          openSubmit() {
            setDialog("submit");
          },
          openReview() {
            setDialog("review");
          },
          async withdraw() {
            const confirmed = await confirm({
              title: t("review.withdraw.title"),
              description: t("review.withdraw.description", { name }),
              okText: t("review.withdraw.ok"),
            });

            if (confirmed) {
              await runReview(
                { action: "withdraw" },
                t("review.toast.withdrawn", { name }),
              );
            }
          },
        }
      : null,
  };

  return (
    <PublishingContext value={controls}>
      {children}
      <>
        {info.pending && (
          <CompareDialog
            open={dialog === "compare"}
            onOpenChange={(open) => setDialog(open ? "compare" : null)}
            model={model}
            resource={resource}
          />
        )}
        <ScheduleDialog
          open={dialog === "schedule"}
          onOpenChange={(open) => {
            setDialog(open ? "schedule" : null);

            if (!open) {
              setApproving(null);
            }
          }}
          name={name}
          info={info}
          unpublish={config.unpublish}
          isPending={busy}
          onSchedule={async (at, unpublishAt) => {
            const dates = {
              at,
              ...(config.unpublish ? { unpublish_at: unpublishAt } : {}),
            };
            const done = approving
              ? await runReview(
                  { action: "approve", ...approving, ...dates },
                  t("review.toast.approved_scheduled", { name }),
                )
              : await run(
                  { action: "schedule", ...dates },
                  t("publishing.toast.scheduled", { name }),
                );

            if (done) {
              setDialog(null);
              setApproving(null);
            }
          }}
        />
        {config.review && (
          <>
            <SubmitDialog
              open={dialog === "submit"}
              onOpenChange={(open) => setDialog(open ? "submit" : null)}
              name={name}
              resourcePath={`${resourcePath}/${resource.id}`}
              again={current?.status === "changes_requested"}
              live={info.state === "published"}
              isPending={busy}
              onSubmit={async (reviewer, note) => {
                const done = await runReview(
                  { action: "submit", reviewer, note },
                  t("review.toast.submitted", { name }),
                );

                if (done) {
                  setDialog(null);
                }
              }}
            />
            <ReviewDialog
              open={dialog === "review"}
              onOpenChange={(open) => setDialog(open ? "review" : null)}
              model={model}
              name={name}
              resourcePath={`${resourcePath}/${resource.id}`}
              live={info.state === "published"}
              isPending={busy}
              onRequestChanges={async (note) => {
                const done = await runReview(
                  { action: "request_changes", note },
                  t("review.toast.changes_requested", { name }),
                );

                if (done) {
                  setDialog(null);
                }
              }}
              onApprove={async (version, note) => {
                const done = await runReview(
                  { action: "approve", version, note },
                  t("review.toast.approved", { name }),
                );

                if (done) {
                  setDialog(null);
                }
              }}
              onApproveAndSchedule={(version, note) => {
                setApproving({ version, note });
                setDialog("schedule");
              }}
            />
          </>
        )}
        {config.unpublish && (
          <UnpublishDateDialog
            open={dialog === "unpublish_at"}
            onOpenChange={(open) => setDialog(open ? "unpublish_at" : null)}
            name={name}
            info={info}
            isPending={isPending}
            onSubmit={async (unpublishAt) => {
              const done = await run(
                { action: "set_unpublish_at", unpublish_at: unpublishAt },
                t(
                  unpublishAt
                    ? "publishing.toast.unpublish_date_set"
                    : "publishing.toast.unpublish_date_removed",
                  { name },
                ),
              );

              if (done) {
                setDialog(null);
              }
            }}
          />
        )}
      </>
    </PublishingContext>
  );
}
