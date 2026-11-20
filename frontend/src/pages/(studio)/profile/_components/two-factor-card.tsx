import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiShieldCheckBold } from "react-icons/pi";
import { toast } from "sonner";

import { useAuth } from "@/auth";
import { Card } from "@/components/analytics/parts";
import {
  CODE_LENGTH,
  TwoFactorCodeInput,
} from "@/components/two-factor/code-input";
import { RecoveryCodes } from "@/components/two-factor/recovery-codes";
import { SetupScan } from "@/components/two-factor/setup-scan";
import { Badge } from "@/components/ui/badge";
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
import { useHttp } from "@/hooks/use-http";
import { formatDate } from "@/lib/format-date";
import { getFieldErrors } from "@/lib/server-errors";
import { getErrorMessage } from "@/lib/utils";

/** The two-factor state on the profile, when the app is installed. */
export interface ProfileTwoFactor {
  enabled: boolean;
  // When it was turned on.
  since: string | null;
  recovery_codes_left: number;
  // The site requires it for this user: it cannot be turned off.
  required: boolean;
}

type DialogName = "setup" | "codes" | "off";

/**
 * Two-factor login on the edit tab: turn it on with the app, get new
 * recovery codes, or turn it off.
 */
export function TwoFactorCard({
  state,
  passwordRequired = false,
}: {
  state: ProfileTwoFactor;
  // Turning it on asks for the current password (the user has one).
  passwordRequired?: boolean;
}) {
  const { t } = useTranslation();
  const [dialog, setDialog] = useState<DialogName | null>(null);
  const onOpenChange = (name: DialogName) => (open: boolean) =>
    setDialog(open ? name : null);

  return (
    <Card
      title={t("two_factor.title")}
      action={
        state.enabled ? (
          <Badge tone="green">
            <PiShieldCheckBold />
            {t("two_factor.on")}
          </Badge>
        ) : (
          <Badge tone="gray">{t("two_factor.off")}</Badge>
        )
      }
    >
      <div className="border-t p-4 flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          {state.enabled
            ? t("two_factor.on_description", {
                date: state.since ? formatDate(new Date(state.since)) : "",
              })
            : t("two_factor.off_description")}
        </p>
        {state.enabled && (
          <p className="text-sm">
            {t("two_factor.codes_left", {
              count: state.recovery_codes_left,
            })}
          </p>
        )}
        {state.required && (
          <p className="text-xs text-muted-foreground">
            {t("two_factor.required_note")}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {state.enabled ? (
            <>
              <Button variant="outline" onClick={() => setDialog("codes")}>
                {t("two_factor.new_codes")}
              </Button>
              {!state.required && (
                <Button variant="ghost" onClick={() => setDialog("off")}>
                  {t("two_factor.turn_off")}
                </Button>
              )}
            </>
          ) : (
            <Button variant="outline" onClick={() => setDialog("setup")}>
              {t("two_factor.turn_on")}
            </Button>
          )}
        </div>
      </div>
      {dialog === "setup" && (
        <SetupDialog
          open
          onOpenChange={onOpenChange("setup")}
          passwordRequired={passwordRequired}
        />
      )}
      {dialog === "codes" && (
        <NewCodesDialog open onOpenChange={onOpenChange("codes")} />
      )}
      {dialog === "off" && (
        <TurnOffDialog open onOpenChange={onOpenChange("off")} />
      )}
    </Card>
  );
}

function fieldError(e: unknown, name = "code"): string {
  const messages = getFieldErrors(e)?.[name];

  if (messages) {
    return Array.isArray(messages) ? messages.join(" ") : String(messages);
  }

  return getErrorMessage(e);
}

/**
 * Turning it on: scan, confirm with a code (and the current password,
 * when the user has one), then the recovery codes.
 */
function SetupDialog({
  open,
  onOpenChange,
  passwordRequired,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  passwordRequired: boolean;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const { setToken } = useAuth();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  // A new secret each time the dialog opens; saved once a code confirms it.
  const { data, error: setupError } = useQuery({
    queryKey: ["profile-two-factor-setup"],
    async queryFn() {
      const { data } = await http.post<{
        secret: string;
        uri: string;
        setup: string;
      }>("/profile/two-factor/setup");
      return data;
    },
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });
  const confirm = useMutation({
    async mutationFn(value: string) {
      try {
        const { data: result } = await http.post<{
          access: string;
          recovery_codes: string[];
        }>("/profile/two-factor/confirm", {
          setup: data?.setup,
          code: value,
          ...(passwordRequired ? { current_password: password } : {}),
        });
        return result;
      } catch (e: unknown) {
        if (getFieldErrors(e)?.current_password) {
          // The code may still be right: only the password is asked again.
          setPasswordError(fieldError(e, "current_password"));
          return null;
        }

        setCode("");
        throw new Error(fieldError(e), { cause: e });
      }
    },
    onSuccess(result) {
      if (!result) {
        return;
      }

      // Turning it on ended the other sessions; this one continues.
      setToken(result.access);
      setCodes(result.recovery_codes);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {codes ? (
          <>
            <DialogHeader>
              <DialogTitle>{t("two_factor.codes_title")}</DialogTitle>
              <DialogDescription>
                {t("two_factor.codes_description")}
              </DialogDescription>
            </DialogHeader>
            <RecoveryCodes codes={codes} />
            <DialogFooter>
              <Button
                onClick={() => {
                  onOpenChange(false);
                  toast.success(t("two_factor.turned_on"));
                }}
              >
                {t("common.done")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{t("two_factor.turn_on")}</DialogTitle>
              <DialogDescription>
                {t("two_factor.setup_dialog_description")}
              </DialogDescription>
            </DialogHeader>
            <form
              id="two-factor-setup"
              className="grid gap-5"
              onSubmit={(event) => {
                event.preventDefault();
                confirm.mutate(code);
              }}
            >
              {setupError ? (
                <p className="text-destructive text-sm">
                  {getErrorMessage(setupError)}
                </p>
              ) : (
                <SetupScan data={data} size={128} />
              )}
              {passwordRequired && (
                <div className="grid gap-1.5">
                  <Label htmlFor="profile-two-factor-password">
                    {t("two_factor.setup_password")}
                  </Label>
                  <Input
                    id="profile-two-factor-password"
                    name="current_password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    aria-invalid={!!passwordError}
                    onChange={(event) => {
                      setPassword(event.target.value);
                      setPasswordError(null);
                    }}
                  />
                  {passwordError && (
                    <p className="text-destructive text-xs">{passwordError}</p>
                  )}
                </div>
              )}
              <div className="grid gap-1.5">
                <Label htmlFor="profile-two-factor-code">
                  {t("two_factor.setup_code")}
                </Label>
                <TwoFactorCodeInput
                  id="profile-two-factor-code"
                  value={code}
                  onChange={setCode}
                  onComplete={(value) => {
                    // Typing the code last confirms; with the password
                    // still empty, Continue does once it is filled in.
                    if (!passwordRequired || password) {
                      confirm.mutate(value);
                    }
                  }}
                  disabled={!data || confirm.isPending}
                  invalid={!!confirm.error}
                  className="justify-start"
                />
                {confirm.error && (
                  <p className="text-destructive text-xs">
                    {confirm.error.message}
                  </p>
                )}
              </div>
            </form>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                type="submit"
                form="two-factor-setup"
                isLoading={confirm.isPending}
                disabled={
                  !data ||
                  code.length < CODE_LENGTH ||
                  (passwordRequired && !password)
                }
              >
                {t("common.continue")}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * A dialog that asks for a code from the app (or a recovery code) to
 * confirm a change.
 */
function CodeConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  submitText,
  destructive,
  isPending,
  error,
  onSubmit,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  title: string;
  description: string;
  submitText: string;
  destructive?: boolean;
  isPending: boolean;
  error: string | null;
  onSubmit(code: string): void;
}) {
  const { t } = useTranslation();
  const [code, setCode] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          id="two-factor-confirm"
          className="grid gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(code);
          }}
        >
          <Label htmlFor="two-factor-confirm-code">
            {t("two_factor.code_or_recovery")}
          </Label>
          <Input
            id="two-factor-confirm-code"
            autoComplete="one-time-code"
            spellCheck={false}
            className="font-mono"
            value={code}
            autoFocus
            aria-invalid={!!error}
            onChange={(e) => setCode(e.target.value)}
          />
          {error && <p className="text-destructive text-xs">{error}</p>}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            form="two-factor-confirm"
            variant={destructive ? "destructive" : "default"}
            isLoading={isPending}
            disabled={!code.trim()}
          >
            {submitText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** New recovery codes: the old ones stop working. */
function NewCodesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const queryClient = useQueryClient();
  const [codes, setCodes] = useState<string[] | null>(null);
  const create = useMutation({
    async mutationFn(code: string) {
      try {
        const { data } = await http.post<{ recovery_codes: string[] }>(
          "/profile/two-factor/recovery-codes",
          { code },
        );
        return data.recovery_codes;
      } catch (e: unknown) {
        throw new Error(fieldError(e), { cause: e });
      }
    },
    onSuccess(result) {
      setCodes(result);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  if (codes) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("two_factor.codes_title")}</DialogTitle>
            <DialogDescription>
              {t("two_factor.new_codes_saved")}
            </DialogDescription>
          </DialogHeader>
          <RecoveryCodes codes={codes} />
          <DialogFooter>
            <Button onClick={() => onOpenChange(false)}>
              {t("common.done")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <CodeConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("two_factor.new_codes")}
      description={t("two_factor.new_codes_description")}
      submitText={t("two_factor.new_codes_submit")}
      isPending={create.isPending}
      error={create.error?.message ?? null}
      onSubmit={(code) => create.mutate(code)}
    />
  );
}

/** Turning it off: a code confirms it. */
function TurnOffDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const { setToken } = useAuth();
  const queryClient = useQueryClient();
  const turnOff = useMutation({
    async mutationFn(code: string) {
      try {
        const { data } = await http.post<{ access: string }>(
          "/profile/two-factor/disable",
          { code },
        );
        return data.access;
      } catch (e: unknown) {
        throw new Error(fieldError(e), { cause: e });
      }
    },
    onSuccess(access) {
      // Turning it off ended the other sessions; this one continues.
      setToken(access);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      toast.success(t("two_factor.turned_off"));
      onOpenChange(false);
    },
  });

  return (
    <CodeConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("two_factor.turn_off_title")}
      description={t("two_factor.turn_off_description")}
      submitText={t("two_factor.turn_off")}
      destructive
      isPending={turnOff.isPending}
      error={turnOff.error?.message ?? null}
      onSubmit={(code) => turnOff.mutate(code)}
    />
  );
}
