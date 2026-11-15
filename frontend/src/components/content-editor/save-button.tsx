import { useTranslation } from "react-i18next";
import { PiCaretDownBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  ButtonGroup,
  ButtonGroupSeparator,
} from "@/components/ui/button-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { isMac } from "@/lib/shortcuts";

// What happens after a save: stay on the object (the default), open an
// empty create form, or go back to the list.
export type SaveMode = "save" | "add_another" | "close";

/**
 * The editor's Save button. Full edit pages split it: the menu next to
 * it saves and adds another, or saves and closes.
 */
export function SaveButton({
  create,
  isSaving,
  addAnother = false,
  close = false,
  onSave,
}: {
  // A create form: the buttons say Create.
  create: boolean;
  isSaving: boolean;
  addAnother?: boolean;
  close?: boolean;
  onSave(mode: SaveMode): void;
}) {
  const { t } = useTranslation();
  const mac = isMac();

  const save = (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          className="min-w-20"
          isLoading={isSaving}
          aria-keyshortcuts={mac ? "Meta+S" : "Control+S"}
          onClick={() => onSave("save")}
        >
          {t(create ? "common.create" : "common.save")}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        <kbd className="font-sans">{mac ? "⌘S" : "Ctrl S"}</kbd>
      </TooltipContent>
    </Tooltip>
  );

  if (!addAnother && !close) {
    return save;
  }

  return (
    <ButtonGroup>
      {save}
      <ButtonGroupSeparator className="bg-primary-foreground/25" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="icon"
            className="w-7"
            disabled={isSaving}
            aria-label={t("editor.save_options")}
          >
            <PiCaretDownBold />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {addAnother && (
            <DropdownMenuItem onSelect={() => onSave("add_another")}>
              {t(
                create
                  ? "editor.create_and_add_another"
                  : "editor.save_and_add_another",
              )}
            </DropdownMenuItem>
          )}
          {close && (
            <DropdownMenuItem onSelect={() => onSave("close")}>
              {t(create ? "editor.create_and_close" : "editor.save_and_close")}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </ButtonGroup>
  );
}
