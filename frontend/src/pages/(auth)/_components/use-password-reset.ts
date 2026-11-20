import * as R from "ramda";

import { useAdminInfo } from "@/hooks/use-admin-info";
import { FieldType, LoginBackendType } from "@/types";

/**
 * Whether editors can reset their password here (the reset app is
 * installed and they log in with an email address), and how long a code
 * stays valid. Undefined while the admin info loads.
 */
export function usePasswordReset() {
  const { data: adminInfo } = useAdminInfo();

  if (!adminInfo) {
    return undefined;
  }

  const config = adminInfo.login_backends.find(
    R.whereEq({ type: LoginBackendType.UsernamePassword }),
  )?.config;
  const available =
    config?.username_field_type === FieldType.EmailField &&
    Boolean(adminInfo.password_reset);

  return {
    available,
    codeMinutes: adminInfo.password_reset?.code_minutes ?? null,
  };
}
