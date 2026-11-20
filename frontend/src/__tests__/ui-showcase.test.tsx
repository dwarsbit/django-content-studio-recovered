import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { isDevtoolsEnabled } from "@/lib/devtools";
import { CatchAllPage } from "@/pages/(studio)/[...slug]/page";

const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("@/pages/(studio)/ui/page", () => ({
  UIPage: () => <div>UI showcase</div>,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function renderAt(path: string, debug: boolean | undefined) {
  useDiscoverMock.mockReturnValue({
    data: { debug, extensions: [], model_groups: [], models: [] },
  });

  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<CatchAllPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllEnvs();
});

// The public page no longer says whether DEBUG is on, so the development
// tools learn it from discover, behind sign-in.
describe("development tools outside the vite dev server", () => {
  it("offers the UI showcase when discover says DEBUG is on", () => {
    vi.stubEnv("DEV", false);
    renderAt("/ui", true);

    expect(screen.getByText("UI showcase")).toBeInTheDocument();
  });

  it("hides the UI showcase without DEBUG", () => {
    vi.stubEnv("DEV", false);
    renderAt("/ui", false);

    expect(screen.queryByText("UI showcase")).not.toBeInTheDocument();
    expect(screen.getByText("app.not_found")).toBeInTheDocument();
  });

  it("turns the developer tools on only when discover says so", () => {
    vi.stubEnv("DEV", false);

    expect(isDevtoolsEnabled(true)).toBe(true);
    expect(isDevtoolsEnabled(false)).toBe(false);
    expect(isDevtoolsEnabled(undefined)).toBe(false);
  });
});
