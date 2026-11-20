import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import { useAuth } from "@/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAdminInfo } from "@/hooks/use-admin-info";
import { useHttp } from "@/hooks/use-http";
import { getErrorMessage, safeRedirectPath } from "@/lib/utils";
import { FieldType, type UsernamePasswordBackend } from "@/types";

import { AuthAlert } from "../../_components/auth-alert";
import { AuthCard } from "../../_components/auth-card";
import { PasswordInput } from "../../_components/password-input";
import { usePasswordVisible } from "../../_components/use-password-visible";
import {
  type TwoFactorChallenge,
  TwoFactorStep,
} from "../_components/two-factor";

export function UsernamePasswordBackend({
  config,
}: {
  config: UsernamePasswordBackend["config"];
}) {
  const { t } = useTranslation();
  const { data: adminInfo } = useAdminInfo();
  const [visible, toggleVisible] = usePasswordVisible();
  const [credentials, setCredentials] = useState({
    username: "",
    password: "",
  });
  const http = useHttp();
  const { setToken } = useAuth();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null);

  function startSession(access: string) {
    setToken(access);
    // The redirect parameter is router-relative (the AuthGuard stores the
    // path without the router basename), so the router resolves it
    // against the mount prefix. Anything but a same-origin path falls
    // back to the dashboard.
    navigate(safeRedirectPath(searchParams.get("redirect")), {
      replace: true,
    });
  }

  const { mutate, isPending, error } = useMutation({
    async mutationFn(credentials: { username: string; password: string }) {
      try {
        const { data } = await http.post<
          { access: string } | { two_factor: TwoFactorChallenge }
        >("/login/usernamepassword", credentials);

        // Two-factor login: the session waits for the code.
        if ("two_factor" in data) {
          setChallenge(data.two_factor);
          return;
        }

        startSession(data.access);
      } catch (e: unknown) {
        throw new Error(getErrorMessage(e), { cause: e });
      }
    },
  });
  const emailField = config.username_field_type === FieldType.EmailField;
  // Resetting a password needs the reset app, and an email to send to.
  const canReset = emailField && Boolean(adminInfo?.password_reset);
  // The reset flow ends here, with the new password still to type.
  const passwordChanged =
    (location.state as { notice?: string } | null)?.notice ===
    "password_changed";

  if (challenge) {
    return (
      <TwoFactorStep
        challenge={challenge}
        onSession={startSession}
        onBack={() => {
          setChallenge(null);
          setCredentials({ ...credentials, password: "" });
        }}
      />
    );
  }

  return (
    <AuthCard
      title={t("login.title", {
        site: adminInfo?.site_title || "Content Studio",
      })}
      description={t(emailField ? "login.subtitle_email" : "login.subtitle")}
      footer={t("login.no_account")}
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          mutate(credentials);
        }}
      >
        {error ? (
          <AuthAlert variant="error">{error.message}</AuthAlert>
        ) : (
          passwordChanged && (
            <AuthAlert variant="success">
              <span>
                <span className="font-medium">
                  {t("login.password_changed")}
                </span>{" "}
                {t("login.password_changed_hint")}
              </span>
            </AuthAlert>
          )
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="login-username">
            {t(emailField ? "login.email" : "login.username")}
          </Label>
          <Input
            id="login-username"
            size="lg"
            type={emailField ? "email" : "text"}
            autoComplete="username"
            placeholder={emailField ? t("login.email_placeholder") : undefined}
            value={credentials.username}
            disabled={isPending}
            autoFocus
            onChange={(e) =>
              setCredentials({ ...credentials, username: e.target.value })
            }
          />
        </div>
        <PasswordInput
          id="login-password"
          label={t("login.password")}
          autoComplete="current-password"
          value={credentials.password}
          visible={visible}
          onToggle={toggleVisible}
          disabled={isPending}
          onChange={(password) => setCredentials({ ...credentials, password })}
          labelAside={
            canReset && (
              <Link
                to={
                  credentials.username
                    ? `/forgot-password?${new URLSearchParams({ email: credentials.username })}`
                    : "/forgot-password"
                }
                className="text-xs font-medium hover:underline"
              >
                {t("login.forgot_password")}
              </Link>
            )
          }
        />
        <Button
          type="submit"
          size="lg"
          className="mt-1 h-10 w-full"
          isLoading={isPending}
        >
          {t("login.submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
