import { useTranslation } from "react-i18next";
import type { Blocker } from "react-router";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

/**
 * Asks before a list with pending in-place edits pages, searches or
 * navigates away (WIP prototype of list_edit).
 */
export function ListEditGuard({
  blocker,
  count,
  onSave,
  onDiscard,
}: {
  blocker: Blocker;
  count: number;
  onSave(): Promise<void>;
  onDiscard(): void;
}) {
  const { t } = useTranslation();

  return (
    <AlertDialog
      open={blocker.state === "blocked"}
      onOpenChange={(open) => !open && blocker.reset?.()}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("list_edit.guard_title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("list_edit.guard_body", { count })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="ghost" onClick={() => blocker.reset?.()}>
            {t("list_edit.guard_keep")}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              onDiscard();
              blocker.proceed?.();
            }}
          >
            {t("list_edit.guard_discard")}
          </Button>
          <Button
            onClick={async () => {
              await onSave();
              blocker.proceed?.();
            }}
          >
            {t("list_edit.save")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
