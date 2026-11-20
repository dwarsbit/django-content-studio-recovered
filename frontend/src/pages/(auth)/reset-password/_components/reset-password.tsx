import { useMutation } from "@tanstack/react-query";
import { REGEXP_ONLY_DIGITS } from "input-otp";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import { Label } from "@/components/ui/label";
import { useHttp } from "@/hooks/use-http";
import { getFieldErrors } from "@/lib/server-errors";
import { getErrorMessage } from "@/lib/utils";

import { AuthAlert } from "../../_components/auth-alert";
import { AuthCard, AuthSteps } from "../../_components/auth-card";
import { PasswordInput, PasswordRules } from "../../_components/password-input";
import { usePasswordVisible } from "../../_components/use-password-visible";

const CODE_LENGTH = 6;

/**
 * Steps 2 and 3 of the reset: the code from the email, then the new
 * password. Saving it leads back to the login page.
 */
export function ResetPassword({ codeMinutes }: { codeMinutes: number | null }) {
  const [searchParams] = useSearchParams();
  const email = searchParams.get("email") ?? "";
  const [code, setCode] = useState<string | null>(null);

  return code === null ? (
    <CodeStep email={email} codeMinutes={codeMinutes} onValid={setCode} />
  ) : (
    <PasswordStep email={email} code={code} />
  );
}

function CodeStep({
  email,
  codeMinutes,
  onValid,
}: {
  email: string;
  codeMinutes: number | null;
  onValid(code: string): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const [code, setCode] = useState("");
  const check = useMutation({
    async mutationFn(code: string) {
      try {
        await http.post("/password-reset/code", { email, code });
      } catch (e: unknown) {
        throw new Error(getErrorMessage(e), { cause: e });
      }
      return code;
    },
    onSuccess: onValid,
  });
  const resend = useMutation({
    async mutationFn() {
      await http.post("/password-reset/request", { email });
    },
    onSuccess() {
      toast.success(t("reset_password.code_resent"));
    },
    onError(e) {
      toast.error(getErrorMessage(e));
    },
  });

  return (
    <AuthCard
      aside={<AuthSteps current={2} total={3} />}
      title={t("reset_password.title")}
      description={
        <>
          {t("reset_password.code_sent_to")}{" "}
          <span className="font-medium text-foreground">{email}</span>.{" "}
          <Link
            to={`/forgot-password?${new URLSearchParams({ email })}`}
            className="font-medium text-foreground hover:underline"
          >
            {t("reset_password.other_email")}
          </Link>
        </>
      }
      footer={
        <>
          {t("reset_password.no_email")}{" "}
          <button
            type="button"
            className="font-medium text-foreground hover:underline disabled:opacity-50"
            disabled={resend.isPending}
            onClick={() => resend.mutate()}
          >
            {t("reset_password.resend")}
          </button>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          check.mutate(code);
        }}
      >
        {check.error && (
          <AuthAlert variant="error">{check.error.message}</AuthAlert>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="reset-code">{t("reset_password.code")}</Label>
          <InputOTP
            id="reset-code"
            maxLength={CODE_LENGTH}
            pattern={REGEXP_ONLY_DIGITS}
            value={code}
            onChange={setCode}
            onComplete={(value: string) => check.mutate(value)}
            disabled={check.isPending}
            autoFocus
            containerClassName="justify-between"
          >
            {Array.from({ length: CODE_LENGTH }, (_, index) => (
              <InputOTPGroup key={index}>
                <InputOTPSlot
                  index={index}
                  className="size-10 text-lg font-medium"
                />
              </InputOTPGroup>
            ))}
          </InputOTP>
          {codeMinutes !== null && (
            <p className="text-xs text-muted-foreground">
              {t("reset_password.code_valid", { count: codeMinutes })}
            </p>
          )}
        </div>
        <Button
          type="submit"
          size="lg"
          className="mt-1 h-10 w-full"
          isLoading={check.isPending}
          disabled={code.length < CODE_LENGTH}
        >
          {t("common.continue")}
        </Button>
      </form>
    </AuthCard>
  );
}

function PasswordStep({ email, code }: { email: string; code: string }) {
  const { t } = useTranslation();
  const http = useHttp();
  const navigate = useNavigate();
  const [visible, toggleVisible] = usePasswordVisible();
  const [values, setValues] = useState({ password: "", confirm: "" });
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>(
    {},
  );
  const [error, setError] = useState<string | null>(null);
  const { mutateAsync: submit, isPending } = useMutation({
    async mutationFn(password: string) {
      await http.post("/password-reset/submit", { email, code, password });
    },
  });

  function update(field: "password" | "confirm", value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function onSubmit() {
    if (values.password !== values.confirm) {
      setErrors({ confirm: t("set_password.mismatch") });
      return;
    }

    setError(null);

    try {
      await submit(values.password);
      navigate("/login", {
        replace: true,
        state: { notice: "password_changed" },
      });
    } catch (e: unknown) {
      const messages = getFieldErrors(e)?.password;

      if (messages) {
        setErrors({
          password: Array.isArray(messages)
            ? messages.join(" ")
            : String(messages),
        });
      } else {
        setError(getErrorMessage(e));
      }
    }
  }

  return (
    <AuthCard
      aside={<AuthSteps current={3} total={3} />}
      title={t("reset_password.new_title")}
      description={
        <>
          {t("reset_password.for")}{" "}
          <span className="font-medium text-foreground">{email}</span>.
        </>
      }
      footer={t("reset_password.logs_out")}
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        {error && <AuthAlert variant="error">{error}</AuthAlert>}
        {/* The email, for password managers to save the new password with. */}
        <input
          type="text"
          name="username"
          autoComplete="username"
          value={email}
          readOnly
          hidden
        />
        <PasswordInput
          id="reset-new-password"
          label={t("reset_password.new")}
          autoComplete="new-password"
          value={values.password}
          visible={visible}
          onToggle={toggleVisible}
          error={errors.password}
          onChange={(value) => update("password", value)}
        >
          <PasswordRules />
        </PasswordInput>
        <PasswordInput
          id="reset-confirm-password"
          label={t("reset_password.confirm")}
          autoComplete="new-password"
          value={values.confirm}
          visible={visible}
          error={errors.confirm}
          onChange={(value) => update("confirm", value)}
        />
        <Button
          type="submit"
          size="lg"
          className="mt-1 h-10 w-full"
          isLoading={isPending}
          disabled={!values.password || !values.confirm}
        >
          {t("reset_password.submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
