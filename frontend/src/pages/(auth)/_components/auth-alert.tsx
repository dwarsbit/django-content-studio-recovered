import type { ReactNode } from "react";
import { PiCheckCircleBold, PiWarningCircleBold } from "react-icons/pi";

import { Alert, AlertDescription } from "@/components/ui/alert";

/** A message at the top of an auth card: an error, or a confirmation. */
export function AuthAlert({
  variant,
  children,
}: {
  variant: "error" | "success";
  children: ReactNode;
}) {
  return variant === "error" ? (
    <Alert
      variant="destructive"
      className="border-transparent bg-destructive/10"
    >
      <PiWarningCircleBold />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  ) : (
    <Alert className="[&>svg]:text-success">
      <PiCheckCircleBold />
      <AlertDescription className="text-foreground">
        {children}
      </AlertDescription>
    </Alert>
  );
}
