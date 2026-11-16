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
  DropdownMenuShortcut,
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

const LABELS: Record<SaveMode, { save: string; create: string }> = {
  save: { save: "common.save", create: "common.create" },
  add_another: {
    save: "editor.save_and_add_another",
    create: "editor.create_and_add_another",
  },
  close: { save: "editor.save_and_close", create: "editor.create_and_close" },
};

/**
 * The editor's Save button. Full edit pages split it: the button does
 * the editor's default save action (a preference on the profile), the
 * menu next to it the others. ⌘S/Ctrl S always saves and stays.
 */
export function SaveButton({
  create,
  isSaving,
  addAnother = false,
  close = false,
  defaultMode = "save",
  onSave,
}: {
  // A create form: the buttons say Create.
  create: boolean;
  isSaving: boolean;
  addAnother?: boolean;
  close?: boolean;
  // What the button does; one the editor does not offer falls back to
  // a plain save.
  defaultMode?: SaveMode;
  onSave(mode: SaveMode): void;
}) {
  const { t } = useTranslation();
  const mac = isMac();
  const shortcut = mac ? "⌘S" : "Ctrl S";
  const modes: SaveMode[] = [
    "save",
    ...(addAnother ? (["add_another"] as const) : []),
    ...(close ? (["close"] as const) : []),
  ];
  const main = modes.includes(defaultMode) ? defaultMode : "save";
  const label = (mode: SaveMode) => t(LABELS[mode][create ? "create" : "save"]);

  const button = (
    <Button
      className="min-w-20"
      isLoading={isSaving}
      aria-keyshortcuts={
        main === "save" ? (mac ? "Meta+S" : "Control+S") : undefined
      }
      onClick={() => onSave(main)}
    >
      {label(main)}
    </Button>
  );

  // The shortcut shows where it applies: on the button when it saves
  // and stays, in the menu otherwise.
  const save =
    main === "save" ? (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={6}>
          <kbd className="font-sans">{shortcut}</kbd>
        </TooltipContent>
      </Tooltip>
    ) : (
      button
    );

  if (modes.length === 1) {
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
          {modes
            .filter((mode) => mode !== main)
            .map((mode) => (
              <DropdownMenuItem key={mode} onSelect={() => onSave(mode)}>
                {label(mode)}
                {mode === "save" && (
                  <DropdownMenuShortcut className="pl-4 tracking-normal">
                    {shortcut}
                  </DropdownMenuShortcut>
                )}
              </DropdownMenuItem>
            ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </ButtonGroup>
  );
}
