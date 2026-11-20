import { useAdminInfo } from "@/hooks/use-admin-info";
import { LoginBackendType } from "@/types";

import { UsernamePasswordBackend } from "./_backends/username-password";

export function LoginPage() {
  const { data: adminInfo } = useAdminInfo();

  return adminInfo
    ? adminInfo.login_backends.map((backend) => {
        switch (backend.type) {
          case LoginBackendType.UsernamePassword:
            return (
              <UsernamePasswordBackend
                key={backend.type}
                config={backend.config}
              />
            );
          default:
            return null;
        }
      })
    : null;
}
