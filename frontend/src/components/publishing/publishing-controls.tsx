import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import useConfirmDialog from "@/hooks/use-confirm-dialog";
import { useHttp } from "@/hooks/use-http";
import { getErrorMessage } from "@/lib/utils";
import type { Model, PublishingInfo, Resource } from "@/types";

import { CompareDialog } from "./compare-dialog";
import {
  type PublishingAction,
  PublishingContext,
  type PublishingControls,
} from "./publishing";
import { ScheduleDialog, UnpublishDateDialog } from "./schedule-dialog";

// The first message of a refused change: a field's (at, unpublish_at)
// or the request's.
function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;

  if (data && typeof data === "object" && !Array.isArray(data)) {
    for (const key of ["at", "unpublish_at", "non_field_errors"]) {
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
  const [dialog, setDialog] = useState<
    "schedule" | "unpublish_at" | "compare" | null
  >(null);
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

  // On studios with pending_changes, saving a live object keeps the
  // changes unpublished until Publish changes.
  const holdsChanges = !!config.pending_changes && info.state === "published";

  const controls: PublishingControls = {
    info,
    unpublish: config.unpublish,
    canPublish: info.can_publish ?? config.can_publish,
    isPending,
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
          onOpenChange={(open) => setDialog(open ? "schedule" : null)}
          name={name}
          info={info}
          unpublish={config.unpublish}
          isPending={isPending}
          onSchedule={async (at, unpublishAt) => {
            const done = await run(
              {
                action: "schedule",
                at,
                ...(config.unpublish ? { unpublish_at: unpublishAt } : {}),
              },
              t("publishing.toast.scheduled", { name }),
            );

            if (done) {
              setDialog(null);
            }
          }}
        />
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
