import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { useSaveShortcut } from "@/components/content-editor/save-shortcut";
import { ContentEditorPage } from "@/pages/(studio)/content/[model]/[id]/page";
import type { FormField, Model, Resource } from "@/types";
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
    t: (key: string, options?: { object?: string }) =>
      options?.object ? `${key}:${options.object}` : key,
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

function makeModel({
  duplicate = true,
  addPermission = true,
}: { duplicate?: boolean; addPermission?: boolean } = {}): Model {
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
        prepopulated_fields: { slug: ["title"] },
        duplicate,
        inlines: [],
      },
      permissions: {
        add_permission: addPermission,
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

const hello = { id: 7, title: "Hello", slug: "hello", __str__: "Hello" };

function mockApi(saveAction = "save") {
  httpMock.get.mockImplementation((url: string) =>
    Promise.resolve({
      data:
        url === "/content/testapp.article/7"
          ? hello
          : url === "/profile"
            ? { preferences: { save_action: saveAction } }
            : [],
    }),
  );
  httpMock.put.mockImplementation((_url: string, values: object) =>
    Promise.resolve({
      data: { ...hello, ...values, __str__: (values as Resource).title },
    }),
  );
  httpMock.post.mockImplementation((_url: string, values: object) =>
    Promise.resolve({ data: { ...values, id: 8, __str__: "Fresh" } }),
  );
}

async function openSaveMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "editor.save_options" }));
}

describe("Save options", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useDiscoverMock.mockReturnValue({ data: makeDiscover(makeModel()) });
    mockApi();
  });

  it("offers save and add another and save and close next to Save", async () => {
    const user = userEvent.setup();
    renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("hello");

    await openSaveMenu(user);

    expect(
      await screen.findByRole("menuitem", {
        name: "editor.save_and_add_another",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "editor.save_and_close" }),
    ).toBeInTheDocument();
  });

  it("leaves out save and add another without add permission", async () => {
    useDiscoverMock.mockReturnValue({
      data: makeDiscover(makeModel({ addPermission: false })),
    });
    const user = userEvent.setup();
    renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("hello");

    await openSaveMenu(user);

    expect(
      await screen.findByRole("menuitem", { name: "editor.save_and_close" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "editor.save_and_add_another" }),
    ).not.toBeInTheDocument();
  });

  it("saves and opens an empty create form", async () => {
    const user = userEvent.setup();
    const router = renderEditor("/content/testapp.article/7");
    const title = await screen.findByDisplayValue("Hello");
    await user.type(title, "!");

    await openSaveMenu(user);
    await user.click(
      await screen.findByRole("menuitem", {
        name: "editor.save_and_add_another",
      }),
    );

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        "/content/testapp.article/new",
      ),
    );
    expect(httpMock.put).toHaveBeenCalledWith(
      "/content/testapp.article/7",
      expect.objectContaining({ title: "Hello!" }),
    );
    expect(toast.success).toHaveBeenCalledWith(
      "editor.saved:Hello!",
      expect.objectContaining({
        action: expect.objectContaining({ label: "editor.open" }),
      }),
    );
    expect(
      await screen.findByRole("button", { name: "common.create" }),
    ).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Hello!")).not.toBeInTheDocument();
    // The leave guard let the navigation through.
    expect(screen.queryByText("editor.unsaved_alert")).not.toBeInTheDocument();
  });

  it("creates and opens another empty create form", async () => {
    const user = userEvent.setup();
    const router = renderEditor("/content/testapp.article/new");
    const [title] = await screen.findAllByRole("textbox");
    await user.type(title, "Fresh");

    await openSaveMenu(user);
    await user.click(
      await screen.findByRole("menuitem", {
        name: "editor.create_and_add_another",
      }),
    );

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith(
        "/content/testapp.article",
        expect.objectContaining({ title: "Fresh" }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByDisplayValue("Fresh")).not.toBeInTheDocument(),
    );
    expect(router.state.location.pathname).toBe("/content/testapp.article/new");
    expect(toast.success).toHaveBeenCalledWith(
      "editor.created:Fresh",
      expect.anything(),
    );
    expect(
      screen.getByRole("button", { name: "common.create" }),
    ).toBeInTheDocument();
  });

  it("saves and goes back to the list", async () => {
    const user = userEvent.setup();
    const router = renderEditor("/content/testapp.article/7");
    const title = await screen.findByDisplayValue("Hello");
    await user.type(title, "!");

    await openSaveMenu(user);
    await user.click(
      await screen.findByRole("menuitem", { name: "editor.save_and_close" }),
    );

    expect(await screen.findByText("list page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/content/testapp.article");
    expect(httpMock.put).toHaveBeenCalledTimes(1);
  });

  it("does not leave when the save fails", async () => {
    httpMock.put.mockRejectedValue(new Error("Nope"));
    const user = userEvent.setup();
    const router = renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("hello");

    await openSaveMenu(user);
    await user.click(
      await screen.findByRole("menuitem", { name: "editor.save_and_close" }),
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(router.state.location.pathname).toBe("/content/testapp.article/7");
  });
});

describe("Default save action", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useDiscoverMock.mockReturnValue({ data: makeDiscover(makeModel()) });
  });

  it("makes the button save and close, with Save in the menu", async () => {
    mockApi("close");
    const user = userEvent.setup();
    const router = renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("hello");

    await openSaveMenu(user);
    expect(
      await screen.findByRole("menuitem", { name: /common\.save/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "editor.save_and_add_another" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "editor.save_and_close" }),
    ).not.toBeInTheDocument();
    await user.keyboard("{Escape}");

    await user.click(
      await screen.findByRole("button", { name: "editor.save_and_close" }),
    );

    expect(await screen.findByText("list page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/content/testapp.article");
  });

  it("keeps Ctrl+S a plain save", async () => {
    mockApi("add_another");
    const router = renderEditor("/content/testapp.article/7");
    const title = await screen.findByDisplayValue("Hello");
    await screen.findByRole("button", { name: "editor.save_and_add_another" });

    title.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "s",
        ctrlKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );

    await waitFor(() => expect(httpMock.put).toHaveBeenCalled());
    expect(router.state.location.pathname).toBe("/content/testapp.article/7");
  });

  it("falls back to Save where add another is not offered", async () => {
    mockApi("add_another");
    useDiscoverMock.mockReturnValue({
      data: makeDiscover(makeModel({ addPermission: false })),
    });
    renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("hello");
    // The preference has loaded once the editor shows the object.
    await waitFor(() => expect(httpMock.get).toHaveBeenCalledWith("/profile"));

    expect(
      screen.getByRole("button", { name: "common.save" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "editor.save_and_add_another" }),
    ).not.toBeInTheDocument();
  });
});

describe("Ctrl+S", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useDiscoverMock.mockReturnValue({ data: makeDiscover(makeModel()) });
    mockApi();
  });

  it("saves from a field and keeps the editor open", async () => {
    const user = userEvent.setup();
    const router = renderEditor("/content/testapp.article/7");
    const title = await screen.findByDisplayValue("Hello");
    await user.type(title, "!");

    const event = new KeyboardEvent("keydown", {
      key: "s",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    title.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    await waitFor(() =>
      expect(httpMock.put).toHaveBeenCalledWith(
        "/content/testapp.article/7",
        expect.objectContaining({ title: "Hello!" }),
      ),
    );
    expect(router.state.location.pathname).toBe("/content/testapp.article/7");
    // The field gets its focus back.
    await waitFor(() => expect(title).toHaveFocus());
  });

  it("works with ⌘ and from outside the fields", async () => {
    const user = userEvent.setup();
    renderEditor("/content/testapp.article/new");
    const [title] = await screen.findAllByRole("textbox");
    await user.type(title, "Fresh");
    title.blur();

    await user.keyboard("{Meta>}s{/Meta}");

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith(
        "/content/testapp.article",
        expect.objectContaining({ title: "Fresh" }),
      ),
    );
  });

  it("leaves Ctrl+Shift+S to the browser", async () => {
    renderEditor("/content/testapp.article/7");
    const title = await screen.findByDisplayValue("Hello");

    const event = new KeyboardEvent("keydown", {
      key: "S",
      ctrlKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    title.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(httpMock.put).not.toHaveBeenCalled();
  });

  it("does not save the editor under a confirm dialog", async () => {
    const user = userEvent.setup();
    renderEditor("/content/testapp.article/7");
    await screen.findByDisplayValue("hello");
    await user.click(
      screen.getByRole("button", { name: "editor.more_actions" }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "common.delete" }),
    );
    await screen.findByRole("alertdialog");

    await user.keyboard("{Control>}s{/Control}");

    expect(httpMock.put).not.toHaveBeenCalled();
  });
});

describe("useSaveShortcut", () => {
  function press() {
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "s", ctrlKey: true }),
    );
  }

  function register(element: HTMLElement, save: () => void) {
    return renderHook(() => {
      const root = useRef<HTMLElement | null>(element);
      useSaveShortcut(root, save);
    });
  }

  it("saves the editor that opened last and is not covered", () => {
    const page = document.body.appendChild(document.createElement("div"));
    const dialog = document.body.appendChild(document.createElement("div"));
    const savePage = vi.fn();
    const saveDialog = vi.fn();
    register(page, savePage);
    const dialogHook = register(dialog, saveDialog);

    press();
    expect(saveDialog).toHaveBeenCalledTimes(1);
    expect(savePage).not.toHaveBeenCalled();

    // A modal over the dialog hides it.
    dialog.setAttribute("aria-hidden", "true");
    page.setAttribute("aria-hidden", "true");
    press();
    expect(saveDialog).toHaveBeenCalledTimes(1);
    expect(savePage).not.toHaveBeenCalled();

    // The dialog closes: the page saves again.
    page.removeAttribute("aria-hidden");
    dialogHook.unmount();
    press();
    expect(savePage).toHaveBeenCalledTimes(1);

    page.remove();
    dialog.remove();
  });
});
