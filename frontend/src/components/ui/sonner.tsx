import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useTheme } from "@/components/theme-provider";
import { useDevtoolsVisible } from "@/lib/devtools";

const Toaster = ({ ...props }: ToasterProps) => {
  // The admin's own theme, not the OS one: sonner picks some of its
  // colors by it, so a mismatch made them unreadable.
  const { theme } = useTheme();
  // Toasts sit above the developer tools button while it shows.
  const devtools = useDevtoolsVisible();

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      offset={devtools ? { bottom: 76 } : undefined}
      mobileOffset={devtools ? { bottom: 76 } : undefined}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
