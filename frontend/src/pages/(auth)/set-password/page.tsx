import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiLinkBreakBold } from "react-icons/pi";
import { Link, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { useAuth } from "@/auth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useAdminInfo } from "@/hooks/use-admin-info";
import { useHttp } from "@/hooks/use-http";
import { getFieldErrors } from "@/lib/server-errors";
import { getErrorMessage, getInitials } from "@/lib/utils";

import { AuthCard } from "../_components/auth-card";
import { PasswordInput, PasswordRules } from "../_components/password-input";
import { usePasswordVisible } from "../_components/use-password-visible";
import {
  type TwoFactorChallenge,
  TwoFactorStep,
} from "../login/_components/two-factor";

interface LinkUser {
  username: string;
  name: string;
  // The user never logged in: the link is their invite.
  invite: boolean;
}

/**
 * The page an emailed link opens (an invite, or a link an admin sent):
 * choose a password, which logs the user in.
 */
export function SetPasswordPage() {
  const { t } = useTranslation();
  const http = useHttp();
  const navigate = useNavigate();
  const { setToken } = useAuth();
  const { data: adminInfo } = useAdminInfo();
  const [searchParams] = useSearchParams();
  const link = {
    uid: searchParams.get("uid") ?? "",
    token: searchParams.get("token") ?? "",
  };
  const [values, setValues] = useState({ password: "", confirm: "" });
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>(
    {},
  );
  const [visible, toggleVisible] = usePasswordVisible();
  // With two-factor login on, the session waits for the code step.
  const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null);

  const { data: user, isPending: isChecking } = useQuery({
    retry: false,
    refetchOnWindowFocus: false,
    queryKey: ["set-password", link],
    async queryFn() {
      try {
        const { data } = await http.post<LinkUser>("/set-password/check", link);
        return data;
      } catch {
        return null;
      }
    },
  });

  const { mutateAsync: submit, isPending } = useMutation({
    async mutationFn(password: string) {
      const { data } = await http.post<
        { access: string } | { two_factor: TwoFactorChallenge }
      >("/set-password", {
        ...link,
        password,
      });
      return data;
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

    try {
      const data = await submit(values.password);

      if ("two_factor" in data) {
        setChallenge(data.two_factor);
        return;
      }

      startSession(data.access);
    } catch (e: unknown) {
      const messages = getFieldErrors(e)?.password;

      if (messages) {
        setErrors({
          password: Array.isArray(messages)
            ? messages.join(" ")
            : String(messages),
        });
      } else {
        toast.error(getErrorMessage(e));
      }
    }
  }

  function startSession(access: string) {
    setToken(access);
    toast.success(t("set_password.done"));
    navigate("/", { replace: true });
  }

  if (challenge) {
    return (
      <TwoFactorStep
        challenge={challenge}
        onSession={startSession}
        // The password is set: logging in again takes it.
        onBack={() => navigate("/login", { replace: true })}
      />
    );
  }

  if (isChecking) {
    return <Spinner className="text-muted-foreground" />;
  }

  if (!user) {
    return (
      <AuthCard
        aside={
          <div className="flex size-10 items-center justify-center rounded-lg border bg-muted text-muted-foreground">
            <PiLinkBreakBold className="size-[18px]" />
          </div>
        }
        title={t("set_password.invalid_title")}
        description={t("set_password.invalid")}
      >
        <Button asChild variant="outline" size="lg" className="h-10 w-full">
          <Link to="/login">{t("auth.to_login")}</Link>
        </Button>
      </AuthCard>
    );
  }

  const site = adminInfo?.site_title || "Content Studio";

  return (
    <AuthCard
      title={
        user.invite
          ? t("set_password.welcome", { name: user.name })
          : t("set_password.title")
      }
      description={
        user.invite
          ? t("set_password.invite_subtitle", { site })
          : t("set_password.subtitle")
      }
      footer={t("set_password.once")}
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="flex items-center gap-3 rounded-lg border bg-muted px-3 py-2.5">
          <Avatar className="size-9 border">
            <AvatarFallback className="bg-card text-xs font-semibold text-secondary-foreground">
              {getInitials(user.name || user.username)}
            </AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-medium">{user.name}</span>
            {user.name !== user.username && (
              <span className="truncate text-xs text-muted-foreground">
                {user.username}
              </span>
            )}
          </div>
        </div>
        {/* The username, for password managers to save the new
            password with. */}
        <input
          type="text"
          name="username"
          autoComplete="username"
          value={user.username}
          readOnly
          hidden
        />
        <PasswordInput
          id="set-password-new"
          label={t("set_password.new")}
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
          id="set-password-confirm"
          label={t("set_password.confirm")}
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
          {t("set_password.submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
