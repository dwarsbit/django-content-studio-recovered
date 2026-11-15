import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ActionFormDialog } from "@/components/action-form-dialog";
import useConfirmDialog from "@/hooks/use-confirm-dialog";
import { useHttp } from "@/hooks/use-http";
import type { ActionValues } from "@/lib/action-form";
import { getErrorMessage } from "@/lib/utils";
import type { BulkAction, Model } from "@/types";

interface Pending {
  action: BulkAction;
  ids: string[];
  // The object a row action runs on, as the list names it.
  name?: string;
  onDone?(): void;
}

/**
 * Runs a bulk or row action on objects of the model, through the bulk
 * endpoint: an action with fields opens its dialog first (its confirm
 * text becomes the dialog's description), other actions confirm when
 * they ask to. The result is shown as a notification and the list is
 * fetched again. Render the returned dialog next to the trigger.
 */
export function useRunAction(model: Model) {
  const { t } = useTranslation();
  const http = useHttp();
  const confirm = useConfirmDialog();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Pending | null>(null);
  const [open, setOpen] = useState(false);

  const { mutateAsync: run, isPending } = useMutation({
    async mutationFn({
      action,
      ids,
      data,
    }: {
      action: BulkAction;
      ids: string[];
      data?: ActionValues;
    }) {
      const { data: result } = await http.post(`/content/${model.label}/bulk`, {
        action: action.id,
        ids,
        ...(data ? { data } : {}),
      });

      return result as { count?: number; message?: string };
    },
    async onSuccess() {
      await queryClient.invalidateQueries({
        queryKey: ["resources", model.label],
      });
    },
  });

  function notify(result: { count?: number; message?: string } | undefined) {
    toast.success(
      result?.message ??
        (result?.count != null
          ? t("bulk.count", { count: result.count })
          : t("bulk.done")),
    );
  }

  async function runAction(
    action: BulkAction,
    ids: string[],
    options: { name?: string; onDone?(): void } = {},
  ) {
    if (action.fields?.length) {
      setPending({ action, ids, name: options.name, onDone: options.onDone });
      setOpen(true);

      return;
    }

    if (action.confirm && !(await confirm({ description: action.confirm }))) {
      return;
    }

    try {
      notify(await run({ action, ids }));
      options.onDone?.();
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  }

  const count = pending?.ids.length ?? 0;
  const description = pending
    ? [
        // A bulk action names the selection; a row action runs on the
        // row it was opened from.
        count > 1
          ? t("actions.selected", {
              count,
              name: model.verbose_name_plural,
            })
          : (pending.name ?? null),
        pending.action.confirm,
      ]
        .filter(Boolean)
        .join(" ")
    : null;

  const dialog = pending?.action.fields ? (
    <ActionFormDialog
      open={open}
      onOpenChange={setOpen}
      title={pending.action.label}
      description={description}
      submitLabel={pending.action.label}
      destructive={pending.action.destructive}
      model={model}
      fields={pending.action.fields}
      onSubmit={async (data) => {
        notify(await run({ action: pending.action, ids: pending.ids, data }));
        pending.onDone?.();
      }}
    />
  ) : null;

  return { runAction, dialog, isPending };
}
