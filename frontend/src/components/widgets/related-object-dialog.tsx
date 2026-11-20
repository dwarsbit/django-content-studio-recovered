import { useTranslation } from "react-i18next";
import { PiPencilSimpleBold, PiPlusBold } from "react-icons/pi";

import { getEditorDialogWidth } from "@/components/content-editor/edit-width";
import { Editor } from "@/components/content-editor/editor";
import { CommandItem } from "@/components/ui/command";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { Model, Resource } from "@/types";

/**
 * The last entry of a relation picker's dropdown: "New <model>", or
 * "Create <model> "<search>"" once something is typed.
 */
export function CreateRelatedItem({
  model,
  search,
  onSelect,
}: {
  model: Model;
  search: string;
  onSelect: VoidFunction;
}) {
  const { t } = useTranslation();
  const text = search.trim();

  return (
    <div className="border-t border-border p-1">
      <CommandItem
        value="__create__"
        onSelect={onSelect}
        className="text-primary data-[selected=true]:text-primary"
      >
        <PiPlusBold className="size-4 text-primary" />
        <span className="line-clamp-1">
          {text
            ? t("widgets.relation_widget.create_named", {
                model: model.verbose_name,
                name: text,
              })
            : t("widgets.relation_widget.create", {
                model: model.verbose_name,
              })}
        </span>
      </CommandItem>
    </div>
  );
}

// Opens the chosen object of a foreign key in the dialog.
export function EditRelatedButton({
  option,
  onClick,
}: {
  option: Resource;
  onClick: VoidFunction;
}) {
  const { t } = useTranslation();

  return (
    <button
      type="button"
      aria-label={t("widgets.relation_widget.edit", { item: option.__str__ })}
      onClick={onClick}
      className="shrink-0 rounded-md size-9 border border-border hover:border-ring flex items-center justify-center text-muted-foreground hover:text-foreground cursor-pointer outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <PiPencilSimpleBold className="size-4" />
    </button>
  );
}

/**
 * The related model's create (or edit) form in a dialog, with that
 * studio's layout, widgets, validation and save hooks. The parent form
 * stays as it is underneath, and pickers in the dialog can open a dialog
 * of their own.
 */
export function RelatedObjectDialog({
  model,
  id,
  prefill,
  readOnly,
  open,
  onOpenChange,
  onSaved,
}: {
  model: Model;
  id?: string;
  prefill?: Record<string, unknown>;
  readOnly: boolean;
  open: boolean;
  onOpenChange(open: boolean): void;
  onSaved(resource: Resource): Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          getEditorDialogWidth(model, model.admin.edit.width),
          "p-0 overflow-hidden flex flex-col",
        )}
        showCloseButton={false}
      >
        <Editor
          dialog
          modelLabel={model.label}
          id={id}
          prefill={prefill}
          readOnly={readOnly}
          canDelete={false}
          onSave={async (saved) => {
            onOpenChange(false);
            if (saved) {
              await onSaved(saved);
            }
          }}
          onClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
