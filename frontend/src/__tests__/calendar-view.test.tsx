import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModelListPage } from "@/pages/(studio)/content/[model]/page";
import type { CalendarViewConfig, Model, Resource } from "@/types";
import { FieldType } from "@/types";

const httpGetMock = vi.hoisted(() => vi.fn());
const httpPostMock = vi.hoisted(() => vi.fn());
const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({ get: httpGetMock, post: httpPostMock }),
}));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: undefined }),
}));
vi.mock("@/hooks/use-confirm-dialog", () => ({ default: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count !== undefined ? `${key}:${options.count}` : key,
    i18n: { language: "en-GB" },
  }),
}));

const calendar: CalendarViewConfig = {
  type: "calendar",
  key: "calendar:published_at",
  field: "published_at",
  end: null,
  label: "Published at",
  date_only: false,
  nullable: true,
  publishing: false,
  editable: true,
};

function makeModel(): Model {
  return {
    label: "testapp.article",
    verbose_name: "Article",
    verbose_name_plural: "Articles",
    tenant_field: null,
    admin: {
      is_singleton: false,
      icon: null,
      list: {
        per_page: 10,
        description: "",
        display: [{ name: "title", header: null, format: null }],
        views: ["table", calendar],
        search: true,
        filter: [],
        sortable_by: null,
        actions: [],
      },
      edit: { main: [], sidebar: [], inlines: [] },
      permissions: {
        add_permission: true,
        change_permission: true,
        delete_permission: true,
        view_permission: true,
      },
    },
    fields: { title: { type: FieldType.CharField, verbose_name: "Title" } },
  } as Model;
}

const row = (id: string, title: string, published_at: string | null) =>
  ({
    id,
    __str__: title,
    title,
    published_at,
    list_item_display: { title },
  }) as Resource;

const dated = [
  row("1", "Ferry notes", new Date(2026, 10, 12, 9, 30).toISOString()),
  row("2", "Night walk", new Date(2026, 10, 12, 18, 0).toISOString()),
];
const undated = [row("3", "Someday", null)];

function LocationProbe() {
  return <span data-testid="search">{useLocation().search}</span>;
}

function renderPage(entry = "/content/testapp.article") {
  useDiscoverMock.mockReturnValue({ data: { models: [makeModel()] } });

  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[entry]}>
        <LocationProbe />
        <Routes>
          <Route path="/content/:model" element={<ModelListPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function calendarCalls() {
  return httpGetMock.mock.calls.filter(([url]) =>
    String(url).endsWith("/calendar"),
  ) as [string, { params: Record<string, unknown> }][];
}

describe("CalendarView", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 21, 10));
    // A British browser: weeks start on Monday.
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["en-GB"]);
    localStorage.clear();
    httpGetMock.mockReset();
    httpGetMock.mockImplementation(
      (url: string, options?: { params?: Record<string, unknown> }) => {
        if (url.endsWith("/calendar")) {
          return Promise.resolve({
            data: options?.params?.unscheduled
              ? { results: undated, count: 1, truncated: false }
              : { results: dated, truncated: false },
          });
        }
        return Promise.resolve({
          data: {
            results: [...dated, ...undated],
            pagination: {
              count: 3,
              approximate: false,
              current: 1,
              pages: 1,
              has_next: false,
            },
          },
        });
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("switches to the calendar and shows the month's items by day", async () => {
    renderPage();

    await userEvent.click(await screen.findByTitle("list_view.calendar_view"));

    const day = await screen.findByRole("gridcell", {
      name: /Thursday,? 12 November 2026/,
    });
    expect(within(day).getByText("Ferry notes")).toBeInTheDocument();
    expect(within(day).getByText("09:30")).toBeInTheDocument();
    expect(within(day).getByText("Night walk")).toBeInTheDocument();
    expect(localStorage.getItem("__dcs_list_view__:testapp.article")).toBe(
      "calendar:published_at",
    );

    const [, { params }] = calendarCalls().find(
      ([, options]) => !options.params.unscheduled,
    )!;
    expect(params.view).toBe("calendar:published_at");
    // A Monday-first locale: the grid runs from 26 October to 7 December.
    expect(new Date(String(params.from)).getTime()).toBe(
      new Date(2026, 9, 26).getTime(),
    );
    expect(new Date(String(params.to)).getTime()).toBe(
      new Date(2026, 11, 7).getTime(),
    );
  });

  it("lists items without a date in the tray", async () => {
    localStorage.setItem(
      "__dcs_list_view__:testapp.article",
      "calendar:published_at",
    );
    renderPage();

    const tray = await screen.findByRole("complementary", {
      name: "list_view.calendar.undated_title",
    });
    expect(await within(tray).findByText("Someday")).toBeInTheDocument();
    expect(
      within(tray).getByText("list_view.calendar.hint_date"),
    ).toBeVisible();
  });

  it("pages by month through the URL", async () => {
    localStorage.setItem(
      "__dcs_list_view__:testapp.article",
      "calendar:published_at",
    );
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "list_view.calendar.next" }),
    );

    expect(screen.getByTestId("search")).toHaveTextContent("?month=2026-12");
    await waitFor(() =>
      expect(
        calendarCalls().some(
          ([, { params }]) =>
            new Date(String(params.from)).getTime() ===
            new Date(2026, 10, 30).getTime(),
        ),
      ).toBe(true),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "list_view.calendar.today" }),
    );
    expect(screen.getByTestId("search")).toHaveTextContent("");
  });

  it("hides the list's pagination", async () => {
    localStorage.setItem(
      "__dcs_list_view__:testapp.article",
      "calendar:published_at",
    );
    renderPage();

    await screen.findByText("Ferry notes");
    expect(
      screen.queryByRole("navigation", { name: "Pagination" }),
    ).not.toBeInTheDocument();
  });
});
