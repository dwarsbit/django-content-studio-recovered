import { useAdminInfo } from "@/hooks/use-admin-info";

/** The environment badge (content_studio.branding), or null without one. */
export function useEnvironment() {
  const { data: adminInfo } = useAdminInfo();

  return adminInfo?.branding?.environment ?? null;
}

/** Whether the site has a logo (SiteLogo renders one). */
export function useHasLogo() {
  const { data: adminInfo } = useAdminInfo();

  return Boolean(adminInfo?.branding?.logo || adminInfo?.branding?.logo_dark);
}
