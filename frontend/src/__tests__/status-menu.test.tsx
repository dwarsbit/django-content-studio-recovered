import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { ValueDialogProvider } from "@/components/value-dialog-provider";
import { MainMenu } from "@/pages/(studio)/_components/main-menu";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: undefined }),
}));
vi.mock("@/hooks/use-me", () => ({
  useMe: () => ({
    data: { username: "leon", first_name: "", last_name: "" },
  }),
}));
vi.mock("@/auth", () => ({ useAuth: () => ({ logout: vi.fn() }) }));
vi.mock("@/components/theme-provider", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function discover(enabled: boolean | undefined) {
  useDiscoverMock.mockReturnValue({
    data: {
      extensions: [],
      model_groups: [],
      models: [],
      media_library: { enabled: false },
      status: enabled === undefined ? undefined : { enabled },
    },
  });
}

function summary(status: string) {
  httpMock.get.mockImplementation((url: string) =>
    url === "/status/summary"
      ? Promise.resolve({
          data: { status, checked_at: "2026-11-20T09:00:00Z" },
        })
      : Promise.reject(new Error(url)),
  );
}

function renderMenu() {
  const router = createMemoryRouter([
    {
      path: "*",
      element: (
        <ConfirmDialogProvider>
          <ValueDialogProvider>
            <MainMenu onOpenPalette={vi.fn()} />
          </ValueDialogProvider>
        </ConfirmDialogProvider>
      ),
    },
  ]);

  render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  return router;
}

describe("System status in the user menu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("opens the status page from the user menu", async () => {
    const user = userEvent.setup();
    discover(true);
    summary("ok");
    const router = renderMenu();

    await user.click(screen.getByRole("button", { name: /leon/ }));
    await user.click(
      await screen.findByRole("menuitem", { name: "main_menu.status" }),
    );

    expect(router.state.location.pathname).toBe("/status");
    // Nothing is wrong: no dot.
    expect(document.querySelector("[data-slot=status-dot]")).toBeNull();
  });

  it.each(["degraded", "down"])(
    "shows a dot on the avatar while a service is %s",
    async (status) => {
      discover(true);
      summary(status);
      renderMenu();

      expect(
        await screen.findByRole("img", { name: `status.summary.${status}` }),
      ).toBeVisible();
    },
  );

  it("leaves the item out and asks nothing without the status page", async () => {
    const user = userEvent.setup();
    discover(false);
    renderMenu();

    await user.click(screen.getByRole("button", { name: /leon/ }));

    expect(
      await screen.findByRole("menuitem", { name: "main_menu.profile" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("menuitem", { name: "main_menu.status" }),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(httpMock.get).not.toHaveBeenCalledWith("/status/summary"),
    );
  });
});
