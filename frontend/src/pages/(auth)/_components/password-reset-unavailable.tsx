import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";

import { AuthCard } from "./auth-card";

/**
 * The reset pages without the reset app, or when users log in with a
 * username: there is no email address to send a code to.
 */
export function PasswordResetUnavailable() {
  const { t } = useTranslation();

  return (
    <AuthCard
      title={t("forgot_password.unavailable_title")}
      description={t("forgot_password.unavailable")}
    >
      <Button asChild variant="outline" size="lg" className="h-10 w-full">
        <Link to="/login">{t("auth.to_login")}</Link>
      </Button>
    </AuthCard>
  );
}
