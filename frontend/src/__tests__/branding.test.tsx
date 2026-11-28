import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { ValueDialogProvider } from "@/components/value-dialog-provider";
import { AuthCard } from "@/pages/(auth)/_components/auth-card";
import { UsernamePasswordBackend } from "@/pages/(auth)/login/_backends/username-password";
import { MainMenu } from "@/pages/(studio)/_components/main-menu";
import { type Branding, FieldType } from "@/types";

const adminInfo = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
}));

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: adminInfo.current }),
}));
vi.mock("@/hooks/use-discover", () => ({
  useDiscover: () => ({
    data: {
      extensions: [],
      model_groups: [],
      models: [],
      media_library: { enabled: false },
    },
  }),
}));
vi.mock("@/hooks/use-me", () => ({ useMe: () => ({ data: undefined }) }));
vi.mock("@/components/theme-provider", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const NO_BRANDING: Branding = {
  logo: null,
  logo_dark: null,
  login_text: null,
  environment: null,
};

function brand(branding: Partial<Branding>) {
  adminInfo.current = {
    site_header: "Northbound",
    site_title: "Northbound CMS",
    branding: { ...NO_BRANDING, ...branding },
  };
}

function renderIn(element: React.ReactNode) {
  const router = createMemoryRouter([{ path: "*", element }]);

  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ConfirmDialogProvider>
        <ValueDialogProvider>
          <RouterProvider router={router} />
        </ValueDialogProvider>
      </ConfirmDialogProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  brand({});
});

describe("Main menu branding", () => {
  it("shows the letter mark and no badge without branding", () => {
    renderIn(<MainMenu onOpenPalette={vi.fn()} />);

    expect(screen.getByText("N")).toBeInTheDocument();
    expect(screen.queryByTestId("environment-badge")).not.toBeInTheDocument();
  });

  it("shows the logo and the environment badge", () => {
    brand({
      logo: "/static/northbound/logo.svg",
      environment: { label: "Staging", color: "yellow" },
    });
    const { container } = renderIn(<MainMenu onOpenPalette={vi.fn()} />);

    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "/static/northbound/logo.svg",
    );
    expect(screen.queryByText("N")).not.toBeInTheDocument();
    expect(screen.getByTestId("environment-badge")).toHaveTextContent(
      "Staging",
    );
    expect(screen.getByText("Northbound")).toBeInTheDocument();
  });

  it("shows the dark logo in the dark theme only", () => {
    brand({
      logo: "/static/logo.svg",
      logo_dark: "/static/logo-dark.svg",
    });
    const { container } = renderIn(<MainMenu onOpenPalette={vi.fn()} />);
    const images = container.querySelectorAll("img");

    expect(images).toHaveLength(2);
    expect(images[0]).toHaveClass("dark:hidden");
    expect(images[1]).toHaveAttribute("src", "/static/logo-dark.svg");
    expect(images[1]).toHaveClass("hidden", "dark:block");
  });

  it("puts a dot on the mark and the label in the expand button when collapsed", () => {
    localStorage.setItem("main-menu-collapsed", "true");
    brand({ environment: { label: "Staging", color: "yellow" } });
    renderIn(<MainMenu onOpenPalette={vi.fn()} />);

    expect(screen.getByTestId("environment-dot")).toHaveClass("bg-amber-500");
    expect(
      screen.getByRole("button", { name: "main_menu.expand · Staging" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("environment-badge")).not.toBeInTheDocument();
  });
});

describe("Login page branding", () => {
  it("shows the logo and the badge on the card", () => {
    brand({
      logo: "/static/northbound/logo.svg",
      environment: { label: "Staging", color: "yellow" },
    });
    const { container } = renderIn(<AuthCard title="Log in" />);

    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "/static/northbound/logo.svg",
    );
    expect(screen.getByTestId("environment-badge")).toHaveTextContent(
      "Staging",
    );
  });

  it("keeps the Content Studio icon without a logo", () => {
    const { container } = renderIn(<AuthCard title="Log in" />);

    expect(container.querySelector("img")?.getAttribute("src")).toMatch(
      /img\/icon\.svg$/,
    );
    expect(screen.queryByTestId("environment-badge")).not.toBeInTheDocument();
  });

  it("replaces the line under the title with the login text", () => {
    brand({ login_text: "Use your Northbound account." });
    renderIn(
      <UsernamePasswordBackend
        config={{ username_field_type: FieldType.CharField }}
      />,
    );

    expect(
      screen.getByText("Use your Northbound account."),
    ).toBeInTheDocument();
    expect(screen.queryByText("login.subtitle")).not.toBeInTheDocument();
  });

  it("keeps the default line without login text", () => {
    renderIn(
      <UsernamePasswordBackend
        config={{ username_field_type: FieldType.CharField }}
      />,
    );

    expect(screen.getByText("login.subtitle")).toBeInTheDocument();
  });
});
