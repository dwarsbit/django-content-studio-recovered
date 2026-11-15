import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getDateLocale } from "@/lib/languages";
import { MainMenu } from "@/pages/(studio)/_components/main-menu";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
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
vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: undefined }),
}));
vi.mock("@/hooks/use-me", () => ({
  useMe: () => ({ data: { username: "leon", first_name: "", last_name: "" } }),
}));
vi.mock("@/auth", () => ({ useAuth: () => ({ logout: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/components/theme-provider", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "de" } }),
}));

const LANGUAGES = [
  { code: "en", locale: "en", name: "English" },
  { code: "de", locale: "de", name: "Deutsch" },
  { code: "fr", locale: "fr", name: "Français" },
];

function setPageLanguages(languages: unknown) {
  document.getElementById("dcs-languages")?.remove();

  if (languages !== undefined) {
    const script = document.createElement("script");
    script.id = "dcs-languages";
    script.type = "application/json";
    script.textContent = JSON.stringify(languages);
    document.head.appendChild(script);
  }
}

function renderMenu() {
  const router = createMemoryRouter([
    { path: "*", element: <MainMenu onOpenPalette={vi.fn()} /> },
  ]);

  render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("Language picker", () => {
  const location = window.location;
  const reload = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...location, reload },
    });
  });

  afterEach(() => {
    setPageLanguages(undefined);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: location,
    });
  });

  it("shows the current language and switches with a reload", async () => {
    setPageLanguages(LANGUAGES);
    httpMock.post.mockResolvedValue({ data: { language: "fr" } });
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByText("leon"));
    const trigger = await screen.findByRole("menuitem", {
      name: /main_menu.language/,
    });
    expect(trigger).toHaveTextContent("Deutsch");

    await user.click(trigger);
    const options = await screen.findAllByRole("menuitemradio");
    expect(options.map((option) => option.textContent)).toEqual([
      "English",
      "Deutsch",
      "Français",
    ]);
    expect(
      screen.getByRole("menuitemradio", { name: "Deutsch" }),
    ).toHaveAttribute("aria-checked", "true");

    // Radix's submenu closes on a pointer leaving its trigger in jsdom:
    // pick the option with the keyboard, as a keyboard user does.
    screen.getByRole("menuitemradio", { name: "Français" }).focus();
    await user.keyboard("{Enter}");

    expect(httpMock.post).toHaveBeenCalledWith("/language", { language: "fr" });
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it("says so when the language could not be changed", async () => {
    setPageLanguages(LANGUAGES);
    httpMock.post.mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByText("leon"));
    await user.click(
      await screen.findByRole("menuitem", { name: /main_menu.language/ }),
    );
    (await screen.findByRole("menuitemradio", { name: "English" })).focus();
    await user.keyboard("{Enter}");

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith("main_menu.language_failed"),
    );
    expect(reload).not.toHaveBeenCalled();
  });

  it("is hidden when the project offers one language", async () => {
    setPageLanguages([LANGUAGES[0]]);
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByText("leon"));
    await screen.findByRole("menuitem", { name: /main_menu.profile/ });

    expect(
      screen.queryByRole("menuitem", { name: /main_menu.language/ }),
    ).not.toBeInTheDocument();
  });

  it("ignores a broken language list", async () => {
    setPageLanguages(undefined);
    const script = document.createElement("script");
    script.id = "dcs-languages";
    script.type = "application/json";
    script.textContent = "{not json";
    document.head.appendChild(script);
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByText("leon"));
    await screen.findByRole("menuitem", { name: /main_menu.profile/ });

    expect(
      screen.queryByRole("menuitem", { name: /main_menu.language/ }),
    ).not.toBeInTheDocument();
  });
});

describe("Date locales", () => {
  it("follows the language, its generic language, or English", () => {
    expect(getDateLocale("fr").code).toBe("fr");
    expect(getDateLocale("pt-BR").code).toBe("pt-BR");
    expect(getDateLocale("de-AT").code).toBe("de");
    expect(getDateLocale("ja").code).toBe("en-US");
    expect(getDateLocale(undefined).code).toBe("en-US");
  });
});
