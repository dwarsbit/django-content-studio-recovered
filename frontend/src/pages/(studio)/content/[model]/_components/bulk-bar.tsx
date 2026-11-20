import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ExportMenu } from "@/components/export-menu";
import { BulkBar } from "@/components/ui/bulk-bar";
import { Button } from "@/components/ui/button";
import { useExport } from "@/hooks/use-export";
import { useRunAction } from "@/hooks/use-run-action";
import { getDownloadErrorMessage } from "@/lib/download";
import { cn } from "@/lib/utils";
import type { BulkAction, ExportFormat, Model } from "@/types";

/**
 * The bulk bar: shown while rows are selected in the table view, it
 * runs the model's bulk actions on the selection. Confirmations come
 * from the action itself (a server-side string), an action with fields
 * asks for its values in a dialog first, and the selection is cleared
 * after a successful action. The built-in export downloads the
 * selection, in the list's ordering, and keeps it selected.
 */
export function ContentBulkBar({
  model,
  actions,
  ids,
  ordering,
  onDone,
}: {
  model: Model;
  actions: BulkAction[];
  ids: string[];
  ordering?: string | null;
  onDone(): void;
}) {
  const { t } = useTranslation();
  const { runAction, dialog, isPending } = useRunAction(model);

  const { mutateAsync: runExport, isPending: isExporting } = useExport(
    model.label,
  );

  async function exportSelection(format: ExportFormat) {
    try {
      await runExport({ format, ids, ordering });
    } catch (e) {
      toast.error(await getDownloadErrorMessage(e));
    }
  }

  return (
    <BulkBar
      label={t("bulk.selected", { count: ids.length })}
      clearLabel={t("bulk.clear")}
      onClear={onDone}
    >
      {actions.map((action) =>
        action.formats ? (
          <ExportMenu
            key={action.id}
            formats={action.formats}
            icon={action.icon}
            variant="ghost"
            disabled={isPending || isExporting}
            onExport={exportSelection}
          />
        ) : (
          <Button
            key={action.id}
            size="sm"
            variant="ghost"
            disabled={isPending || isExporting}
            className={cn({
              "text-destructive hover:bg-destructive/10 hover:text-destructive":
                action.destructive,
            })}
            onClick={() => runAction(action, ids, { onDone })}
          >
            {action.icon && <span className={cn(action.icon, "text-sm")} />}
            {action.label}
          </Button>
        ),
      )}
      {dialog}
    </BulkBar>
  );
}
