import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { EnvironmentBadge, SiteLogo } from "@/components/branding";
import { useHasLogo } from "@/hooks/use-branding";
import { cn } from "@/lib/utils";

/**
 * The card every page before logging in is built from: the app icon (with
 * an optional element beside it), a title, a description, the page's
 * content and an optional footer strip for secondary information.
 */
export function AuthCard({
  title,
  description,
  aside,
  footer,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  aside?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
}) {
  const hasLogo = useHasLogo();

  return (
    <div className="w-full max-w-[400px] overflow-hidden rounded-2xl border bg-card text-card-foreground shadow-xl">
      <div className="flex flex-col gap-6 p-6 sm:p-8">
        <div className="flex items-center justify-between gap-3">
          {hasLogo ? (
            <SiteLogo className="size-10 rounded-lg" />
          ) : (
            <img
              src={`${window.DCS_STATIC_PREFIX ?? ""}img/icon.svg`}
              alt=""
              className="size-10"
            />
          )}
          <div className="flex items-center gap-3">
            {aside}
            <EnvironmentBadge />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <h1 className="text-xl leading-tight font-semibold tracking-tight">
            {title}
          </h1>
          {description && (
            <p className="text-muted-foreground">{description}</p>
          )}
        </div>
        {children}
      </div>
      {footer && (
        <div className="border-t bg-muted px-6 py-3.5 text-muted-foreground sm:px-8">
          {footer}
        </div>
      )}
    </div>
  );
}

/** "Step 2 of 3" with a bar per step, beside the icon. */
export function AuthSteps({
  current,
  total,
}: {
  current: number;
  total: number;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground select-none">
      <span>{t("auth.step", { current, total })}</span>
      <div aria-hidden className="flex gap-1">
        {Array.from({ length: total }, (_, index) => (
          <span
            key={index}
            className={cn(
              "h-1 w-4 rounded-full",
              index < current ? "bg-foreground" : "bg-border",
            )}
          />
        ))}
      </div>
    </div>
  );
}
