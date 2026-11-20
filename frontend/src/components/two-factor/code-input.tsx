import { REGEXP_ONLY_DIGITS } from "input-otp";

import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import { cn } from "@/lib/utils";

export const CODE_LENGTH = 6;

/** Six boxes for the code from an authenticator app. */
export function TwoFactorCodeInput({
  id,
  value,
  onChange,
  onComplete,
  disabled,
  invalid,
  autoFocus,
  className,
}: {
  id: string;
  value: string;
  onChange(value: string): void;
  onComplete?(value: string): void;
  disabled?: boolean;
  invalid?: boolean;
  autoFocus?: boolean;
  className?: string;
}) {
  return (
    <InputOTP
      id={id}
      maxLength={CODE_LENGTH}
      pattern={REGEXP_ONLY_DIGITS}
      inputMode="numeric"
      autoComplete="one-time-code"
      value={value}
      onChange={onChange}
      onComplete={onComplete}
      disabled={disabled}
      autoFocus={autoFocus}
      containerClassName={cn("justify-between", className)}
    >
      {Array.from({ length: CODE_LENGTH }, (_, index) => (
        <InputOTPGroup key={index}>
          <InputOTPSlot
            index={index}
            aria-invalid={invalid}
            className="size-10 text-lg font-medium"
          />
        </InputOTPGroup>
      ))}
    </InputOTP>
  );
}
