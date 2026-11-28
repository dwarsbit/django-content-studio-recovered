import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuditLogPage } from "@/pages/(studio)/audit-log/page";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && !("defaultValue" in options)
        ? `${key} ${JSON.stringify(options)}`
        : key,
    i18n: { language: "en" },
  }),
}));

const now = new Date().toISOString();

const article = {
  label: "testapp.article",
  verbose_name: "article",
  verbose_name_plural: "articles",
  fields: {
    title: { type: "CharField", verbose_name: "title" },
  },
  admin: {},
};

function change(overrides: Record<string, unknown> = {}) {
  return {
    id: "change-1",
    kind: "change",
    entry_id: 1,
    action: "updated",
    time: now,
    user: { id: 1, username: "root", label: "root" },
    model: "testapp.article",
    model_name: "article",
    object_id: "7",
    object_repr: "Hello world",
    object_exists: true,
    message: "Changed Title.",
    has_version: true,
    ...overrides,
  };
}

function signIn(overrides: Record<string, unknown> = {}) {
  return {
    id: "sign-in-1",
    kind: "sign_in",
    action: "sign_in_failed",
    time: now,
    user: null,
    username: "mallory",
    method: "",
    reason: "wrong_password",
    ip_address: "203.0.113.9",
    browser: "Firefox on macOS",
    user_agent: "Mozilla/5.0",
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}) {
  return {
    entries: [change(), signIn()],
    next: "cursor-1",
    limit: 50,
    options: {
      models: [{ value: "testapp.article", label: "article" }],
      users: [{ value: "1", label: "root", username: "root" }],
      actions: ["created", "updated", "signed_in", "sign_in_failed"],
      export_formats: ["csv", "xlsx"],
      keep_days: null,
      history: true,
    },
    ...overrides,
  };
}

function renderPage(path = "/audit-log") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <AuditLogPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuditLogPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDiscoverMock.mockReturnValue({
      data: { audit_log: { enabled: true }, models: [article] },
    });
  });

  it("lists changes and sign-ins, and loads the next page by cursor", async () => {
    httpMock.get.mockImplementation((url: string, config) => {
      if (config?.params?.after === "cursor-1") {
        return Promise.resolve({
          data: page({
            entries: [change({ id: "change-2", object_repr: "Older" })],
            next: null,
            options: undefined,
          }),
        });
      }
      return Promise.resolve({ data: page() });
    });

    renderPage();

    expect(
      await screen.findByRole("link", { name: "Hello world" }),
    ).toHaveAttribute("href", "/content/testapp.article/7");
    expect(screen.getByText("Changed Title.")).toBeInTheDocument();
    expect(screen.getByText("mallory")).toBeInTheDocument();
    expect(
      screen.getByText("audit_log.reasons.wrong_password"),
    ).toBeInTheDocument();
    expect(screen.getByText("203.0.113.9")).toBeInTheDocument();
    expect(screen.getByText("Firefox on macOS")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "audit_log.load_more" }),
    );

    expect(await screen.findByText("Older")).toBeInTheDocument();
    expect(httpMock.get).toHaveBeenLastCalledWith("/audit-log", {
      params: { after: "cursor-1" },
    });
    expect(
      screen.queryByRole("button", { name: "audit_log.load_more" }),
    ).toBeNull();
  });

  it("passes the filters in the URL to the API", async () => {
    httpMock.get.mockResolvedValue({ data: page({ next: null }) });

    renderPage("/audit-log?model=testapp.article&object=7&action=updated");

    await screen.findByText("Changed Title.");
    expect(httpMock.get).toHaveBeenCalledWith("/audit-log", {
      params: { model: "testapp.article", object: "7", action: "updated" },
    });
    expect(
      screen.getByText('audit_log.object_filter {"name":"Hello world"}'),
    ).toBeInTheDocument();
  });

  it("opens the change of an entry with a version, read-only", async () => {
    httpMock.get.mockImplementation((url: string) =>
      url === "/audit-log/changes/1"
        ? Promise.resolve({
            data: {
              ...change(),
              fields: ["title"],
              previous: { title: "Hello" },
              data: { title: "Hello world" },
            },
          })
        : Promise.resolve({ data: page({ next: null }) }),
    );

    renderPage();

    await userEvent.click(
      (await screen.findByText("Changed Title.")).closest(
        '[role="button"]',
      ) as HTMLElement,
    );

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByTestId("word-diff")).toHaveTextContent(
        "Hello world",
      ),
    );
    expect(
      within(dialog).queryByRole("button", { name: "history.restore" }),
    ).toBeNull();
    expect(
      within(dialog).getByRole("link", { name: "audit_log.open_object" }),
    ).toHaveAttribute("href", "/content/testapp.article/7");
  });

  it("explains when the page is not available", async () => {
    useDiscoverMock.mockReturnValue({
      data: { audit_log: { enabled: false } },
    });

    renderPage();

    expect(
      await screen.findByText("audit_log.unavailable_title"),
    ).toBeInTheDocument();
    expect(httpMock.get).not.toHaveBeenCalled();
  });
});
