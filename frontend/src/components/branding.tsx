import { Badge } from "@/components/ui/badge";
import { useAdminInfo } from "@/hooks/use-admin-info";
import { useEnvironment } from "@/hooks/use-branding";
import { cn } from "@/lib/utils";
import type { BadgeTone } from "@/types";

// The environment dot's color per badge tone, for the collapsed menu.
const DOT_COLORS: Record<BadgeTone, string> = {
  gray: "bg-zinc-400",
  blue: "bg-blue-500",
  green: "bg-green-500",
  yellow: "bg-amber-500",
  red: "bg-red-500",
  purple: "bg-violet-500",
};

/** The pill with the environment's label, such as "Staging". */
export function EnvironmentBadge({ className }: { className?: string }) {
  const environment = useEnvironment();

  if (!environment) {
    return null;
  }

  return (
    <Badge
      tone={environment.color}
      className={className}
      data-testid="environment-badge"
    >
      {environment.label}
    </Badge>
  );
}

/** A dot in the environment's color, for where the label does not fit. */
export function EnvironmentDot({ className }: { className?: string }) {
  const environment = useEnvironment();

  if (!environment) {
    return null;
  }

  return (
    <span
      aria-hidden
      data-testid="environment-dot"
      className={cn(
        "size-2.5 rounded-full ring-2 ring-sidebar",
        DOT_COLORS[environment.color] ?? DOT_COLORS.gray,
        className,
      )}
    />
  );
}

/**
 * The site's logo, with the dark theme's variant when there is one; null
 * when the site has no logo, so the caller shows its own mark.
 */
export function SiteLogo({ className }: { className?: string }) {
  const { data: adminInfo } = useAdminInfo();
  const logo = adminInfo?.branding?.logo;
  const logoDark = adminInfo?.branding?.logo_dark;

  if (!logo && !logoDark) {
    return null;
  }

  if (!logo || !logoDark) {
    return (
      <img
        src={logo ?? logoDark ?? ""}
        alt=""
        className={cn("object-contain", className)}
      />
    );
  }

  return (
    <>
      <img
        src={logo}
        alt=""
        className={cn("object-contain dark:hidden", className)}
      />
      <img
        src={logoDark}
        alt=""
        className={cn("hidden object-contain dark:block", className)}
      />
    </>
  );
}
