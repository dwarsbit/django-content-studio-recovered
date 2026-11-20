import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { PiEyeBold, PiEyeClosedBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAdminInfo } from "@/hooks/use-admin-info";

/**
 * A labelled password field. With `onToggle` it has a button that shows
 * the password; pages with two fields share one `visible` state.
 */
export function PasswordInput({
  id,
  label,
  value,
  onChange,
  autoComplete,
  visible,
  onToggle,
  error,
  disabled,
  labelAside,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange(value: string): void;
  autoComplete: "current-password" | "new-password";
  visible: boolean;
  onToggle?: VoidFunction;
  error?: string;
  disabled?: boolean;
  // Beside the label, such as a "Forgot password?" link.
  labelAside?: ReactNode;
  // Below the field, such as the password rules.
  children?: ReactNode;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        {labelAside}
      </div>
      <div className="relative">
        <Input
          id={id}
          size="lg"
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          className={onToggle ? "pr-10" : undefined}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
        {onToggle && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="absolute top-1/2 right-1.5 -translate-y-1/2 text-muted-foreground"
            aria-label={t(
              visible
                ? "widgets.password_widget.hide"
                : "widgets.password_widget.show",
            )}
            aria-pressed={visible}
            onClick={onToggle}
          >
            {visible ? <PiEyeClosedBold /> : <PiEyeBold />}
          </Button>
        )}
      </div>
      {error && (
        <p id={`${id}-error`} className="text-xs text-destructive">
          {error}
        </p>
      )}
      {children}
    </div>
  );
}

/** The rules of the project's AUTH_PASSWORD_VALIDATORS, as a list. */
export function PasswordRules() {
  const { data: adminInfo } = useAdminInfo();
  const rules = adminInfo?.password_rules ?? [];

  if (rules.length === 0) {
    return null;
  }

  return (
    <ul className="mt-0.5 list-disc pl-4 text-xs text-muted-foreground">
      {rules.map((rule) => (
        <li key={rule}>{rule}</li>
      ))}
    </ul>
  );
}
