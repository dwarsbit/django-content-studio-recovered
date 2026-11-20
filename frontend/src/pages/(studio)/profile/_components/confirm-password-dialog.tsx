import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Asks for the current password before a change that could hand the
 * account over, such as a new email address.
 */
export function ConfirmPasswordDialog({
  open,
  onOpenChange,
  description,
  isPending,
  error,
  onSubmit,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  description: string;
  isPending: boolean;
  error: string | null;
  onSubmit(password: string): void;
}) {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Nothing typed is kept for the next time.
        setPassword("");
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("profile.confirm_password.title")}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          id="confirm-password"
          className="grid gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(password);
          }}
        >
          <Label htmlFor="confirm-password-input">
            {t("profile.password.current")}
          </Label>
          <Input
            id="confirm-password-input"
            name="current_password"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "confirm-password-error" : undefined}
            onChange={(event) => setPassword(event.target.value)}
          />
          {error && (
            <p id="confirm-password-error" className="text-destructive text-xs">
              {error}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            form="confirm-password"
            isLoading={isPending}
            disabled={!password}
          >
            {t("profile.confirm_password.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
