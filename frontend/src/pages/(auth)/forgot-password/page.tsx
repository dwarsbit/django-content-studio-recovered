import { PasswordResetUnavailable } from "../_components/password-reset-unavailable";
import { usePasswordReset } from "../_components/use-password-reset";
import { ForgotPassword } from "./_components/forgot-password";

export function ForgotPasswordPage() {
  const reset = usePasswordReset();

  if (!reset) {
    return null;
  }

  return reset.available ? <ForgotPassword /> : <PasswordResetUnavailable />;
}
