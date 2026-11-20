import { Outlet } from "react-router";

/**
 * The pages before logging in: a card centered on a quiet, dotted page in
 * the current theme.
 */
export function AuthLayout() {
  return (
    <div className="relative isolate flex min-h-screen flex-col items-center gap-6 overflow-hidden bg-sidebar px-4 pt-8 pb-6 dark:bg-background">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 [background-image:radial-gradient(circle_at_1px_1px,color-mix(in_oklab,var(--foreground)_18%,transparent)_1px,transparent_1.5px)] [background-size:22px_22px] [mask-image:radial-gradient(ellipse_640px_500px_at_50%_46%,#000_25%,transparent_100%)]"
      />
      <main className="flex w-full flex-1 flex-col items-center justify-center">
        <Outlet />
      </main>
      <footer className="text-xs text-muted-foreground select-none">
        Django Content Studio
      </footer>
    </div>
  );
}
