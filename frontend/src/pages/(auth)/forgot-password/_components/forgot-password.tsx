import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useHttp } from "@/hooks/use-http";
import { getErrorMessage } from "@/lib/utils";

import { AuthAlert } from "../../_components/auth-alert";
import { AuthCard, AuthSteps } from "../../_components/auth-card";
import { BackToLogin } from "../../_components/back-to-login";

/** Step 1 of the reset: the email address to send a code to. */
export function ForgotPassword() {
  const { t } = useTranslation();
  const http = useHttp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState(searchParams.get("email") ?? "");
  const { mutate, isPending, error } = useMutation({
    async mutationFn(email: string) {
      try {
        await http.post("/password-reset/request", { email });
        navigate(`/reset-password?${new URLSearchParams({ email })}`);
      } catch (e: unknown) {
        throw new Error(getErrorMessage(e), { cause: e });
      }
    },
  });

  return (
    <AuthCard
      aside={<AuthSteps current={1} total={3} />}
      title={t("forgot_password.title")}
      description={t("forgot_password.subtitle")}
      footer={<BackToLogin />}
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          mutate(email);
        }}
      >
        {error && <AuthAlert variant="error">{error.message}</AuthAlert>}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="forgot-email">{t("login.email")}</Label>
          <Input
            id="forgot-email"
            size="lg"
            type="email"
            autoComplete="username"
            placeholder={t("login.email_placeholder")}
            value={email}
            disabled={isPending}
            autoFocus
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <Button
          type="submit"
          size="lg"
          className="mt-1 h-10 w-full"
          isLoading={isPending}
          disabled={!email}
        >
          {t("forgot_password.submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
