import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModelListPage } from "@/pages/(studio)/content/[model]/page";
import type { Model, Resource } from "@/types";
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
        views: ["table", "gallery"],
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

const rows = [
  {
    id: "1",
    __str__: "Ferry notes",
    list_item_display: {
      title: "Ferry notes",
      thumbnail: "/media/ferry.webp",
      meta: "Travel",
    },
  },
  {
    id: "2",
    __str__: "Someday",
    list_item_display: { title: "Someday" },
    __publishing__: { state: "draft", published_at: null },
  },
] as unknown as Resource[];

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

describe("GalleryView", () => {
  beforeEach(() => {
    localStorage.clear();
    httpGetMock.mockReset();
    httpGetMock.mockResolvedValue({
      data: {
        results: rows,
        pagination: {
          count: 2,
          approximate: false,
          current: 1,
          pages: 1,
          has_next: false,
        },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the page as tiles of the list item images", async () => {
    const { container } = renderPage();

    await userEvent.click(await screen.findByTitle("list_view.gallery_view"));

    const tiles = container.querySelectorAll("[data-tile]");
    expect(tiles).toHaveLength(2);
    expect(
      within(tiles[0] as HTMLElement).getByText("Ferry notes"),
    ).toBeInTheDocument();
    expect((tiles[0] as HTMLElement).querySelector("img")).toHaveAttribute(
      "src",
      "/media/ferry.webp",
    );
    expect(
      within(tiles[0] as HTMLElement).getByText("Travel"),
    ).toBeInTheDocument();
    // No image: a placeholder.
    expect(
      within(tiles[1] as HTMLElement).getByTestId("gallery-placeholder"),
    ).toBeInTheDocument();
    expect(localStorage.getItem("__dcs_list_view__:testapp.article")).toBe(
      "gallery",
    );
  });

  it("switches and remembers the tile size", async () => {
    localStorage.setItem("__dcs_list_view__:testapp.article", "gallery");
    const { container } = renderPage();

    await screen.findByText("Ferry notes");
    expect(container.querySelector("ul[data-size]")).toHaveAttribute(
      "data-size",
      "large",
    );

    await userEvent.click(screen.getByTitle("list_view.gallery.small"));

    expect(container.querySelector("ul[data-size]")).toHaveAttribute(
      "data-size",
      "small",
    );
    expect(localStorage.getItem("__dcs_gallery_size__:testapp.article")).toBe(
      "small",
    );
  });
});
