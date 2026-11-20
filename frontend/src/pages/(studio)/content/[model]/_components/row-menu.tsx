import { useTranslation } from "react-i18next";
import { PiDotsThreeVerticalBold } from "react-icons/pi";
import { useNavigate } from "react-router";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Move } from "@/lib/reorder";
import { cn } from "@/lib/utils";
import type { BulkAction, Model } from "@/types";

// The id of the built-in duplicate: it opens the create form with a
// copy instead of running on the server.
const DUPLICATE_ACTION_ID = "duplicate";

const DELETE_ACTION_ID = "delete";

/**
 * A row's ⋯ menu on the list page: the model's row actions for that
 * one object, and the moves when the list can be reordered. Destructive
 * actions come last. Opening the menu never opens the row.
 */
export function RowMenu({
  model,
  id,
  name,
  actions,
  onRunAction,
  move,
  className,
}: {
  model: Model;
  id: string;
  // The object, as the list names it.
  name?: string;
  actions: BulkAction[];
  onRunAction(action: BulkAction, id: string, name?: string): void;
  // Reordering: the moves, why they are off (null when on), and whether
  // the row is the first or last of the whole list.
  move?: {
    onMove(move: Move): void;
    disabledReason?: string | null;
    atStart?: boolean;
    atEnd?: boolean;
  };
  className?: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Delete comes last, also when it moves to the trash.
  const isLast = (action: BulkAction) =>
    action.destructive || action.id === DELETE_ACTION_ID;
  const regular = actions.filter((action) => !isLast(action));
  const destructive = actions.filter(isLast);
  // With only moves, a disabled reorder disables the whole menu, as
  // before row actions.
  const disabled = actions.length === 0 && !!move?.disabledReason;

  function select(action: BulkAction) {
    if (action.id === DUPLICATE_ACTION_ID) {
      navigate(
        `/content/${model.label}/new?duplicate=${encodeURIComponent(id)}`,
      );
    } else {
      onRunAction(action, id, name);
    }
  }

  function item(action: BulkAction) {
    return (
      <DropdownMenuItem
        key={action.id}
        variant={isLast(action) ? "destructive" : "default"}
        className="justify-start"
        onSelect={() => select(action)}
      >
        {action.icon && <span className={cn(action.icon, "text-sm")} />}
        {action.label}
      </DropdownMenuItem>
    );
  }

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger
        disabled={disabled}
        title={disabled ? (move?.disabledReason ?? undefined) : undefined}
        aria-label={
          name ? t("row_actions.menu_for", { name }) : t("row_actions.menu")
        }
        onClick={(event) => event.stopPropagation()}
        className={cn(
          "inline-flex items-center justify-center size-6 rounded-md text-muted-foreground outline-none cursor-pointer",
          "hover:bg-foreground/5 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
          "data-[state=open]:bg-foreground/5 data-[state=open]:text-foreground",
          "disabled:cursor-not-allowed disabled:opacity-40",
          className,
        )}
      >
        <PiDotsThreeVerticalBold />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="min-w-44"
        onClick={(event) => event.stopPropagation()}
      >
        {regular.map(item)}
        {move && (
          <>
            {regular.length > 0 && <DropdownMenuSeparator />}
            <DropdownMenuGroup title={move.disabledReason ?? undefined}>
              {actions.length > 0 && (
                <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">
                  {t("reorder.menu")}
                </DropdownMenuLabel>
              )}
              <DropdownMenuItem
                disabled={!!move.disabledReason || move.atStart}
                onSelect={() => move.onMove({ position: "up" })}
              >
                {t("reorder.move_up")}
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!!move.disabledReason || move.atEnd}
                onSelect={() => move.onMove({ position: "down" })}
              >
                {t("reorder.move_down")}
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!!move.disabledReason || move.atStart}
                onSelect={() => move.onMove({ position: "first" })}
              >
                {t("reorder.move_first")}
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!!move.disabledReason || move.atEnd}
                onSelect={() => move.onMove({ position: "last" })}
              >
                {t("reorder.move_last")}
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </>
        )}
        {destructive.length > 0 && (regular.length > 0 || move) && (
          <DropdownMenuSeparator />
        )}
        {destructive.map(item)}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
