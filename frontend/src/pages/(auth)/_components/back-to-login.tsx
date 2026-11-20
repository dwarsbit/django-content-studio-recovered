import { useTranslation } from "react-i18next";
import { PiArrowLeftBold } from "react-icons/pi";
import { Link } from "react-router";

export function BackToLogin() {
  const { t } = useTranslation();

  return (
    <Link
      to="/login"
      className="inline-flex items-center gap-1.5 font-medium text-foreground hover:underline"
    >
      <PiArrowLeftBold className="size-3.5" />
      {t("auth.back_to_login")}
    </Link>
  );
}
