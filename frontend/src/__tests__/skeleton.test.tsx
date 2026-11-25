import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  render,
  renderHook,
  screen,
  within,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { useSkeleton } from "@/hooks/use-skeleton";
import { ContentEditorPage } from "@/pages/(studio)/content/[model]/[id]/page";
import type { FormField, Model } from "@/types";
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
        [FieldType.TextField]: { name: FieldWidget.TextAreaWidget },
        [FieldType.BooleanField]: { name: FieldWidget.CheckboxWidget },
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

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("useSkeleton", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows nothing for a load quicker than the delay", () => {
    const { result, rerender } = renderHook(
      ({ loading }) => useSkeleton(loading),
      { initialProps: { loading: true } },
    );

    act(() => vi.advanceTimersByTime(150));
    rerender({ loading: false });
    act(() => vi.advanceTimersByTime(500));

    expect(result.current).toBe(false);
  });

  it("shows after the delay and stays at least the minimum time", () => {
    const { result, rerender } = renderHook(
      ({ loading }) => useSkeleton(loading),
      { initialProps: { loading: true } },
    );

    expect(result.current).toBe(false);
    act(() => vi.advanceTimersByTime(200));
    expect(result.current).toBe(true);

    // The data arrives 50ms after the skeleton showed.
    act(() => vi.advanceTimersByTime(50));
    rerender({ loading: false });
    act(() => vi.advanceTimersByTime(200));
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(50));
    expect(result.current).toBe(false);
  });

  it("hides at once when it was shown long enough", () => {
    const { result, rerender } = renderHook(
      ({ loading }) => useSkeleton(loading),
      { initialProps: { loading: true } },
    );

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(true);

    rerender({ loading: false });
    act(() => vi.advanceTimersByTime(0));
    expect(result.current).toBe(false);
  });
});

function field(name: string, label: string | null = null): FormField {
  return {
    type: "field",
    name,
    label,
    readonly: false,
    col_span: 1,
    widget: null,
    component_id: "",
    component_type: "LinkButton",
    copy: false,
    icon: "",
  };
}

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
        display: [],
        search: false,
        filter: [],
        sortable_by: null,
        actions: [],
      },
      edit: {
        main: [
          {
            label: "Content",
            formsets: [
              {
                title: "Story",
                description: "",
                fields: [
                  field("title"),
                  field("body", "Story text"),
                  { ...field("secret"), when: { field: "featured" } as never },
                ],
              },
            ],
          },
          { label: "SEO", formsets: [] },
        ],
        sidebar: [{ title: "", description: "", fields: [field("featured")] }],
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
      title: { type: FieldType.CharField, verbose_name: "Title" },
      body: { type: FieldType.TextField, verbose_name: "Body" },
      secret: { type: FieldType.CharField, verbose_name: "Secret" },
      featured: { type: FieldType.BooleanField, verbose_name: "Featured" },
    },
  } as Model;
}

function renderEditor(path: string) {
  const router = createMemoryRouter(
    [{ path: "/content/:model/:id", element: <ContentEditorPage /> }],
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
}

describe("EditorSkeleton", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useDiscoverMock.mockReturnValue({
      data: {
        dashboard: { widgets: [] },
        extensions: [],
        model_groups: [],
        models: [makeModel()],
        user_model: "auth.User",
        multitenancy: { enabled: false, tenant_model: null },
        media_library: {
          enabled: false,
          folders: false,
          models: { media_model: null, folder_model: null },
        },
      },
    });
  });

  it("shows the studio's layout while the object loads", async () => {
    let resolve!: (value: unknown) => void;
    httpMock.get.mockImplementation((url: string) =>
      url === "/content/testapp.article/7"
        ? new Promise((r) => {
            resolve = r;
          })
        : Promise.resolve({ data: [] }),
    );
    renderEditor("/content/testapp.article/7");

    const skeleton = await screen.findByTestId("editor-skeleton");
    const inSkeleton = within(skeleton);
    expect(inSkeleton.getByText("Articles")).toBeInTheDocument();
    expect(inSkeleton.getByText("Content")).toBeInTheDocument();
    expect(inSkeleton.getByText("SEO")).toBeInTheDocument();
    expect(inSkeleton.getByText("Story")).toBeInTheDocument();
    expect(inSkeleton.getByText("Title")).toBeInTheDocument();
    expect(inSkeleton.getByText("Story text")).toBeInTheDocument();
    expect(inSkeleton.getByText("Featured")).toBeInTheDocument();
    // Whether a conditional field shows depends on the values.
    expect(inSkeleton.queryByText("Secret")).not.toBeInTheDocument();
    expect(
      inSkeleton.getByRole("button", { name: "common.save" }),
    ).toBeDisabled();

    resolve({
      data: {
        id: 7,
        title: "Hello",
        body: "",
        featured: false,
        __str__: "Hello",
      },
    });

    expect(await screen.findByDisplayValue("Hello")).toBeInTheDocument();
    expect(screen.queryByTestId("editor-skeleton")).not.toBeInTheDocument();
  });
});
