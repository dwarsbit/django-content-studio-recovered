import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { PiWarningCircleBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { ListEdit } from "@/hooks/use-list-edit";
import type { Model } from "@/types";

/**
 * The Save bar of a list with pending in-place edits (WIP prototype of
 * list_edit): how many changes wait, Discard and Save. Ctrl/Cmd+S
 * saves, like on the edit page.
 */
export function SaveBar({
  model,
  edit,
  onSave,
}: {
  model: Model;
  edit: ListEdit;
  onSave(): void;
}) {
  const { t } = useTranslation();
  const failed = Object.keys(edit.errors).length;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "s") {
        event.preventDefault();
        onSave();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSave]);

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-5 z-20 flex justify-center px-6">
      <div className="pointer-events-auto flex items-center gap-1 rounded-lg border bg-popover text-popover-foreground shadow-xl pl-3 pr-1.5 py-1.5">
        {failed > 0 ? (
          <span className="flex items-center gap-1.5 select-none text-sm font-medium mr-3 text-destructive">
            <PiWarningCircleBold />
            {t("list_edit.failed", {
              count: failed,
              singular: model.verbose_name,
              plural: model.verbose_name_plural,
            })}
          </span>
        ) : (
          <span className="flex items-center gap-2 select-none text-sm font-medium tabular-nums mr-3">
            <span className="size-2 rounded-full bg-warning" />
            {t("list_edit.pending", {
              count: edit.count,
              rows: edit.rowCount,
              noun:
                edit.rowCount === 1
                  ? model.verbose_name
                  : model.verbose_name_plural,
            })}
          </span>
        )}
        <Button
          size="sm"
          variant="ghost"
          disabled={edit.isSaving}
          onClick={edit.discard}
        >
          {t("list_edit.discard")}
        </Button>
        <Button size="sm" disabled={edit.isSaving} onClick={onSave}>
          {edit.isSaving && <Spinner className="size-3.5" />}
          {t("list_edit.save")}
          <kbd className="ml-1 hidden sm:inline text-[10px] font-medium opacity-70">
            {navigator.platform.includes("Mac") ? "⌘S" : "Ctrl+S"}
          </kbd>
        </Button>
      </div>
    </div>
  );
}
