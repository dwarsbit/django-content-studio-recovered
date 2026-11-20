import { useEffect, useState } from "react";
import { Outlet } from "react-router";

import { CommandPalette } from "@/components/command-palette";
import Devtools from "@/components/devtools/devtools";
import { NotificationSync } from "@/components/notifications/sync";
import { NotificationToasts } from "@/components/notifications/toasts";
import { useDiscover } from "@/hooks/use-discover";
import { http } from "@/hooks/use-http";
import { useNotificationsEnabled } from "@/hooks/use-notifications";
import { installDevtools, isDevtoolsEnabled } from "@/lib/devtools";
import { TenantProvider } from "@/tenant";

import { MainMenu } from "./_components/main-menu";

export function StudioLayout() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const notifications = useNotificationsEnabled();
  const { data: discover } = useDiscover();
  // The developer tools run only while they are on (DEBUG); discover says
  // so, because the public page does not. They are not a lazy chunk: they
  // share most of their modules with the entry, which a lazy chunk may
  // not import (see vite.config.ts).
  const devtoolsEnabled = isDevtoolsEnabled(discover?.devtools);

  if (devtoolsEnabled) {
    // Idempotent, so rendering again does not add interceptors.
    installDevtools(http);
  }

  // ⌘K on macOS, Ctrl+K elsewhere, toggles the command palette.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <TenantProvider>
      <>
        <div className="h-screen flex items-stretch bg-background">
          <MainMenu onOpenPalette={() => setPaletteOpen(true)} />
          <main className="relative flex-1 min-w-0 overflow-hidden bg-background flex flex-col">
            <Outlet />
          </main>
        </div>
        <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
        {notifications && (
          <>
            <NotificationSync />
            <NotificationToasts />
          </>
        )}
        {devtoolsEnabled && <Devtools />}
      </>
    </TenantProvider>
  );
}
