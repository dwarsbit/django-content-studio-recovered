import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiArrowLeftBold } from "react-icons/pi";

import {
  CODE_LENGTH,
  TwoFactorCodeInput,
} from "@/components/two-factor/code-input";
import { RecoveryCodes } from "@/components/two-factor/recovery-codes";
import { SetupScan } from "@/components/two-factor/setup-scan";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAdminInfo } from "@/hooks/use-admin-info";
import { useHttp } from "@/hooks/use-http";
import { getErrorMessage } from "@/lib/utils";

import { AuthAlert } from "../../_components/auth-alert";
import { AuthCard, AuthSteps } from "../../_components/auth-card";

/** What the password step answers when a code is still needed. */
export interface TwoFactorChallenge {
  challenge: string;
  // The account, to show whose code is asked for.
  username: string;
  // The user has no authenticator yet but must use one: set it up first.
  setup_required: boolean;
}

/**
 * The step after the password: the code from the authenticator app, a
 * recovery code instead, or setting up the app when it is required.
 * Only this step's answer carries the session.
 */
export function TwoFactorStep({
  challenge,
  onBack,
  onSession,
}: {
  challenge: TwoFactorChallenge;
  onBack(): void;
  onSession(access: string): void;
}) {
  return challenge.setup_required ? (
    <SetupSteps challenge={challenge} onBack={onBack} onSession={onSession} />
  ) : (
    <CodeStep challenge={challenge} onBack={onBack} onSession={onSession} />
  );
}

function BackButton({ onBack }: { onBack(): void }) {
  const { t } = useTranslation();

  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1.5 font-medium text-foreground hover:underline"
    >
      <PiArrowLeftBold className="size-3.5" />
      {t("auth.back_to_login")}
    </button>
  );
}

function CodeStep({
  challenge,
  onBack,
  onSession,
}: {
  challenge: TwoFactorChallenge;
  onBack(): void;
  onSession(access: string): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const verify = useMutation({
    async mutationFn(value: string) {
      try {
        const { data } = await http.post<{ access: string }>(
          "/two-factor/verify",
          recovery
            ? { challenge: challenge.challenge, recovery_code: value }
            : { challenge: challenge.challenge, code: value },
        );
        return data.access;
      } catch (e: unknown) {
        setCode("");
        throw new Error(getErrorMessage(e), { cause: e });
      }
    },
    onSuccess: onSession,
  });

  return (
    <AuthCard
      title={t(
        recovery ? "two_factor.recovery_title" : "two_factor.code_title",
      )}
      description={
        <>
          {t(
            recovery
              ? "two_factor.recovery_description"
              : "two_factor.code_description",
          )}{" "}
          <span className="font-medium text-foreground">
            {challenge.username}
          </span>
          .
        </>
      }
      footer={t("two_factor.lost_everything")}
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          verify.mutate(code);
        }}
      >
        {verify.error && (
          <AuthAlert variant="error">{verify.error.message}</AuthAlert>
        )}
        {recovery ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="two-factor-recovery">
              {t("two_factor.recovery_code")}
            </Label>
            <Input
              id="two-factor-recovery"
              size="lg"
              autoComplete="off"
              spellCheck={false}
              placeholder="xxxx-xxxx"
              className="font-mono"
              value={code}
              disabled={verify.isPending}
              autoFocus
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="two-factor-code">{t("two_factor.code")}</Label>
            <TwoFactorCodeInput
              id="two-factor-code"
              value={code}
              onChange={setCode}
              onComplete={(value) => verify.mutate(value)}
              disabled={verify.isPending}
              invalid={!!verify.error}
              autoFocus
            />
          </div>
        )}
        <Button
          type="submit"
          size="lg"
          className="mt-1 h-10 w-full"
          isLoading={verify.isPending}
          disabled={recovery ? !code.trim() : code.length < CODE_LENGTH}
        >
          {t("login.submit")}
        </Button>
        <div className="flex items-center justify-between gap-3 text-sm">
          <BackButton onBack={onBack} />
          <button
            type="button"
            className="font-medium text-muted-foreground hover:text-foreground hover:underline"
            onClick={() => {
              setRecovery(!recovery);
              setCode("");
              verify.reset();
            }}
          >
            {t(
              recovery
                ? "two_factor.use_app_instead"
                : "two_factor.use_recovery_instead",
            )}
          </button>
        </div>
      </form>
    </AuthCard>
  );
}

interface SetupData {
  secret: string;
  uri: string;
  // The secret, signed, until a code confirms it.
  setup: string;
}

/**
 * Setting up the app during login, when the site requires it: scan and
 * confirm with a code, then save the recovery codes.
 */
function SetupSteps({
  challenge,
  onBack,
  onSession,
}: {
  challenge: TwoFactorChallenge;
  onBack(): void;
  onSession(access: string): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const { data: adminInfo } = useAdminInfo();
  const site = adminInfo?.site_title || "Content Studio";
  const [code, setCode] = useState("");
  const [done, setDone] = useState<{
    access: string;
    recovery_codes: string[];
  } | null>(null);
  // A new secret per challenge, kept while the step is open.
  const { data = null } = useQuery({
    queryKey: ["two-factor-setup", challenge.challenge],
    async queryFn() {
      const { data } = await http.post<SetupData>("/two-factor/setup", {
        challenge: challenge.challenge,
      });
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
        }>("/two-factor/setup/confirm", {
          challenge: challenge.challenge,
          setup: data?.setup,
          code: value,
        });
        return result;
      } catch (e: unknown) {
        setCode("");
        throw new Error(getErrorMessage(e), { cause: e });
      }
    },
    onSuccess: setDone,
  });

  if (done) {
    return (
      <AuthCard
        aside={<AuthSteps current={2} total={2} />}
        title={t("two_factor.codes_title")}
        description={t("two_factor.codes_description")}
        footer={t("two_factor.codes_footer")}
      >
        <div className="flex flex-col gap-4">
          <RecoveryCodes codes={done.recovery_codes} />
          <Button
            size="lg"
            className="mt-1 h-10 w-full"
            onClick={() => onSession(done.access)}
          >
            {t("two_factor.codes_saved", { site })}
          </Button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      aside={<AuthSteps current={1} total={2} />}
      title={t("two_factor.setup_title")}
      description={t("two_factor.setup_required", { site })}
      footer={<BackButton onBack={onBack} />}
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          confirm.mutate(code);
        }}
      >
        {confirm.error && (
          <AuthAlert variant="error">{confirm.error.message}</AuthAlert>
        )}
        <SetupScan data={data} />
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="two-factor-setup-code">
            {t("two_factor.setup_code")}
          </Label>
          <TwoFactorCodeInput
            id="two-factor-setup-code"
            value={code}
            onChange={setCode}
            onComplete={(value) => confirm.mutate(value)}
            disabled={confirm.isPending || !data}
            invalid={!!confirm.error}
          />
        </div>
        <Button
          type="submit"
          size="lg"
          className="mt-1 h-10 w-full"
          isLoading={confirm.isPending}
          disabled={code.length < CODE_LENGTH}
        >
          {t("common.continue")}
        </Button>
      </form>
    </AuthCard>
  );
}
