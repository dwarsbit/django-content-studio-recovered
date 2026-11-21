import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModelListPage } from "@/pages/(studio)/content/[model]/page";
import type { BoardViewConfig, Model, Resource } from "@/types";
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
    t: (key: string, options?: Record<string, unknown>) =>
      options?.label !== undefined
        ? `${key}:${String(options.label)}`
        : options?.column !== undefined
          ? `${key}:${String(options.column)}`
          : key,
    i18n: { language: "en-GB" },
  }),
}));

const board: BoardViewConfig = {
  type: "board",
  key: "board:author",
  field: "author",
  label: "Author",
  relation: true,
  empty_value: null,
  columns: [
    { value: null, label: "" },
    { value: 1, label: "Ada" },
    { value: 2, label: "Lin" },
  ],
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
        views: ["table", board],
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

const row = (id: string, title: string, author: number | null) =>
  ({
    id,
    __str__: title,
    title,
    author: author === null ? null : { id: author, __str__: "x" },
    list_item_display: { title, description: `About ${title}` },
  }) as Resource;

const columns = (ada: Resource[] = [row("1", "Ferry notes", 1)]) => [
  { value: null, label: "", count: 1, results: [row("3", "Orphan", null)] },
  { value: 1, label: "Ada", count: 25, results: ada },
  { value: 2, label: "Lin", count: 0, results: [] },
];

function renderPage() {
  useDiscoverMock.mockReturnValue({ data: { models: [makeModel()] } });

  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={["/content/testapp.article"]}>
        <Routes>
          <Route path="/content/:model" element={<ModelListPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function boardCalls() {
  return httpGetMock.mock.calls.filter(([url]) =>
    String(url).endsWith("/board"),
  ) as [string, { params: URLSearchParams }][];
}

describe("BoardView", () => {
  beforeEach(() => {
    localStorage.clear();
    httpGetMock.mockReset();
    httpGetMock.mockImplementation((url: string) => {
      if (url.endsWith("/board")) {
        return Promise.resolve({
          data: { columns: columns(), max_per_column: 200 },
        });
      }
      if (url.includes("/presence")) {
        return Promise.resolve({ data: {} });
      }
      return Promise.resolve({
        data: {
          results: [row("1", "Ferry notes", 1)],
          pagination: {
            count: 1,
            approximate: false,
            current: 1,
            pages: 1,
            has_next: false,
          },
        },
      });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("switches to the board and shows a column per value", async () => {
    renderPage();

    await userEvent.click(
      await screen.findByTitle("list_view.board_view:Author"),
    );

    const ada = await screen.findByRole("region", { name: "Ada" });
    expect(within(ada).getByText("Ferry notes")).toBeInTheDocument();
    expect(within(ada).getByText("About Ferry notes")).toBeInTheDocument();
    expect(within(ada).getByText("25")).toBeInTheDocument();

    // Items without an author lead, under "No author".
    const none = screen.getByRole("region", {
      name: "list_view.board.none:author",
    });
    expect(within(none).getByText("Orphan")).toBeInTheDocument();
    expect(localStorage.getItem("__dcs_list_view__:testapp.article")).toBe(
      "board:author",
    );
    expect(boardCalls()[0][1].params.get("view")).toBe("board:author");
    // The board replaces the list's pagination.
    expect(
      screen.queryByRole("navigation", { name: "Pagination" }),
    ).not.toBeInTheDocument();
  });

  it("shows more of a column on request", async () => {
    localStorage.setItem("__dcs_list_view__:testapp.article", "board:author");
    renderPage();

    const ada = await screen.findByRole("region", { name: "Ada" });
    await userEvent.click(
      within(ada).getByRole("button", { name: "list_view.board.show_more" }),
    );

    await waitFor(() =>
      expect(
        boardCalls().some(([, { params }]) =>
          params.getAll("show").includes("1:21"),
        ),
      ).toBe(true),
    );
    // A column with every card shown has no "Show more".
    expect(
      within(screen.getByRole("region", { name: "Lin" })).queryByRole(
        "button",
        { name: "list_view.board.show_more" },
      ),
    ).not.toBeInTheDocument();
  });

  it("offers to add an item to a column", async () => {
    localStorage.setItem("__dcs_list_view__:testapp.article", "board:author");
    renderPage();

    const lin = await screen.findByRole("region", { name: "Lin" });
    expect(
      within(lin).getByRole("button", { name: "list_view.board.add:Lin" }),
    ).toBeInTheDocument();
  });
});
