import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import {
  columnLanguage,
  languageStates,
  translatedName,
} from "@/lib/content-language";
import { ContentEditorPage } from "@/pages/(studio)/content/[model]/[id]/page";
import type { FormField, Model, TranslationConfig } from "@/types";
import { FieldType, FieldWidget } from "@/types";

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));
const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => httpMock,
}));

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({
    data: {
      formats: {},
      widgets: {
        [FieldType.CharField]: { name: FieldWidget.InputWidget },
        [FieldType.SlugField]: { name: FieldWidget.InputWidget },
      },
      settings: {
        created_at_attr: "created_at",
        created_by_attr: "created_by",
        edited_at_attr: "edited_at",
        edited_by_attr: "edited_by",
      },
    },
  }),
}));

vi.mock("@/hooks/use-discover", () => ({
  useDiscover: useDiscoverMock,
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count !== undefined ? `${key}:${options.count}` : key,
  }),
}));

function field(name: string): FormField {
  return {
    type: "field",
    name,
    label: null,
    readonly: false,
    col_span: 1,
    widget: null,
    component_id: "",
    component_type: "LinkButton",
    copy: false,
    icon: "",
  };
}

const config: TranslationConfig = {
  languages: [
    { code: "en", name: "English" },
    { code: "nl", name: "Dutch" },
    { code: "de", name: "German" },
  ],
  default: "en",
  required: ["en"],
  fields: {
    title: { en: "title", nl: "title_nl", de: "title_de" },
  },
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
      translations: config,
      list: {
        per_page: 10,
        description: "",
        display: [],
        search: false,
        filter: [],
        sortable_by: null,
        actions: [],
      },
      edit: {
        main: [
          {
            label: "",
            formsets: [
              {
                title: "",
                description: "",
                fields: [field("title"), field("slug")],
              },
            ],
          },
        ],
        sidebar: [],
        readonly_fields: [],
        prepopulated_fields: {},
        duplicate: false,
        inlines: [],
      },
      permissions: {
        add_permission: true,
        change_permission: true,
        delete_permission: true,
        view_permission: true,
      },
    },
    fields: {
      id: {
        type: FieldType.IntegerField,
        primary_key: true,
        readonly: true,
        verbose_name: "ID",
      },
      title: {
        type: FieldType.CharField,
        verbose_name: "Title",
        default: "",
      },
      title_nl: {
        type: FieldType.CharField,
        verbose_name: "Title (Dutch)",
        default: "",
      },
      title_de: {
        type: FieldType.CharField,
        verbose_name: "Title (German)",
        default: "",
      },
      slug: {
        type: FieldType.SlugField,
        verbose_name: "Slug",
        default: "",
        max_length: 50,
      },
    },
  };
}

function makeDiscover(model: Model) {
  return {
    dashboard: { widgets: [] },
    extensions: [],
    model_groups: [],
    models: [model],
    user_model: "auth.User",
    multitenancy: { enabled: false, tenant_model: null },
    media_library: {
      enabled: false,
      folders: false,
      models: { media_model: null, folder_model: null },
    },
  };
}

function renderEditor(path: string) {
  const router = createMemoryRouter(
    [
      { path: "/content/:model", element: <div>list page</div> },
      { path: "/content/:model/new", element: <ContentEditorPage /> },
      { path: "/content/:model/:id", element: <ContentEditorPage /> },
    ],
    { initialEntries: [path] },
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ConfirmDialogProvider>
        <RouterProvider router={router} />
      </ConfirmDialogProvider>
    </QueryClientProvider>,
  );

  return router;
}

const hello = {
  id: 7,
  title: "Hello",
  title_nl: "Hallo",
  title_de: "",
  slug: "hello",
  __str__: "Hello",
};

function mockApi() {
  httpMock.get.mockImplementation((url: string) =>
    Promise.resolve({
      data:
        url === "/content/testapp.article/7"
          ? hello
          : url === "/profile"
            ? { preferences: {} }
            : [],
    }),
  );
  httpMock.put.mockImplementation((_url: string, values: object) =>
    Promise.resolve({ data: { ...hello, ...values } }),
  );
}

describe("content language helpers", () => {
  it("maps a field to its column in the shown language", () => {
    expect(translatedName(config, "nl", "title")).toEqual({
      name: "title_nl",
      translated: true,
      shared: false,
    });
    expect(translatedName(config, "nl", "slug")).toEqual({
      name: "slug",
      translated: false,
      shared: true,
    });
    expect(translatedName(config, "en", "slug").shared).toBe(false);
    expect(translatedName(null, "", "title").name).toBe("title");
  });

  it("counts each language's empty fields", () => {
    const values: Record<string, unknown> = { title: "Hi", title_nl: "" };

    expect(languageStates(config, (column) => values[column])).toEqual({
      en: { total: 1, missing: 0 },
      nl: { total: 1, missing: 1 },
      de: { total: 1, missing: 1 },
    });
  });

  it("finds a column's language", () => {
    expect(columnLanguage(config, "title_de")).toBe("de");
    expect(columnLanguage(config, "slug")).toBeNull();
  });
});

describe("Translated content in the editor", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    useDiscoverMock.mockReturnValue({ data: makeDiscover(makeModel()) });
    mockApi();
  });

  it("switches the translated fields to the picked language", async () => {
    const user = userEvent.setup();
    renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("Hello");

    await user.click(
      screen.getByRole("button", { name: /translations.content_language/ }),
    );
    const menu = await screen.findByRole("menu");
    // German misses its one translated field; English is complete.
    expect(
      within(menu).getByText("translations.missing_short:1"),
    ).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: /Dutch/ }));

    expect(await screen.findByDisplayValue("Hallo")).toBeInTheDocument();
    // Shared fields keep their value in every language.
    expect(screen.getByDisplayValue("hello")).toBeInTheDocument();
    expect(window.localStorage.getItem("dcs-content-language")).toBe("nl");
  });

  it("copies the default language's text into an empty translation", async () => {
    window.localStorage.setItem("dcs-content-language", "de");
    const user = userEvent.setup();
    renderEditor("/content/testapp.article/7");

    const reference = await screen.findByTestId("translation-reference");
    expect(reference).toHaveTextContent("Hello");

    await user.click(within(reference).getByRole("button"));
    expect(await screen.findByDisplayValue("Hello")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(httpMock.put).toHaveBeenCalledWith(
        "/content/testapp.article/7",
        expect.objectContaining({
          title: "Hello",
          title_nl: "Hallo",
          title_de: "Hello",
        }),
      ),
    );
  });
});
