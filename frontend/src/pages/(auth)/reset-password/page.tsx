import { PasswordResetUnavailable } from "../_components/password-reset-unavailable";
import { usePasswordReset } from "../_components/use-password-reset";
import { ResetPassword } from "./_components/reset-password";

export function ResetPasswordPage() {
  const reset = usePasswordReset();

  if (!reset) {
    return null;
  }

  return reset.available ? (
    <ResetPassword codeMinutes={reset.codeMinutes} />
  ) : (
    <PasswordResetUnavailable />
  );
}
