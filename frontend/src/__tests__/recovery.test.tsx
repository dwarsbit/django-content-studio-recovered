import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { Editor } from "@/components/content-editor/editor";
import {
  clearKept,
  type KeptChanges,
  mergeKept,
  pruneKept,
  readKept,
  recoveryKey,
  writeKept,
} from "@/lib/recovery";
import type { Model, ModelField } from "@/types";
import { FieldType, FieldWidget } from "@/types";

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));
const useAdminInfoMock = vi.hoisted(() => vi.fn());
const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-admin-info", () => ({ useAdminInfo: useAdminInfoMock }));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const KEY = recoveryKey({ user: "7", model: "testapp.article", id: "abc" });
const NEW_KEY = recoveryKey({ user: "7", model: "testapp.article" });

function kept(
  fields: KeptChanges["fields"],
  keptAt = Date.now() - 60_000,
): KeptChanges {
  return { version: 1, keptAt, fields };
}

describe("recovery storage", () => {
  afterEach(() => localStorage.clear());

  it("keys kept changes by tenant, user, model and object", () => {
    expect(KEY).toBe("cs:recovery:-:7:testapp.article:abc");
    expect(NEW_KEY).toBe("cs:recovery:-:7:testapp.article:new");
    expect(
      recoveryKey({ tenant: "t1", user: "7", model: "a.b", id: "1" }),
    ).toBe("cs:recovery:t1:7:a.b:1");
  });

  it("writes and reads kept changes, and ignores what it cannot read", () => {
    const changes = kept({ title: { value: "New", base: "Old" } });

    expect(writeKept(KEY, changes)).toBe(true);
    expect(readKept(KEY)).toEqual(changes);

    localStorage.setItem(KEY, "{not json");
    expect(readKept(KEY)).toBeNull();
    localStorage.setItem(KEY, JSON.stringify({ version: 2, fields: {} }));
    expect(readKept(KEY)).toBeNull();
  });

  it("reports a refused write (storage full or blocked)", () => {
    const setItem = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new DOMException("full", "QuotaExceededError");
      });

    expect(writeKept(KEY, kept({}))).toBe(false);
    setItem.mockRestore();
  });

  it("prunes kept changes older than the max age, and clears them all", () => {
    const day = 24 * 60 * 60 * 1000;
    const now = Date.now();

    writeKept(KEY, kept({}, now - 8 * day));
    writeKept(NEW_KEY, kept({}, now - 2 * day));
    localStorage.setItem("theme", "dark");

    pruneKept(7, now);
    expect(readKept(KEY)).toBeNull();
    expect(readKept(NEW_KEY)).not.toBeNull();

    clearKept();
    expect(readKept(NEW_KEY)).toBeNull();
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("merges kept changes with the object as it is now", () => {
    const changes = kept({
      title: { value: "Mine", base: "Old" },
      lead: { value: "My lead", base: "Lead" },
      body: { value: "Same", base: "Before" },
    });

    expect(
      mergeKept(changes, { title: "Old", lead: "Lead", body: "Before" }),
    ).toEqual({
      clean: ["title", "lead", "body"],
      clashes: [],
      changedSince: false,
    });

    // Someone saved the title (a clash) and the body with my value.
    expect(
      mergeKept(changes, { title: "Theirs", lead: "Lead", body: "Same" }),
    ).toEqual({ clean: ["lead"], clashes: ["title"], changedSince: true });
  });
});

const fields: Record<string, ModelField> = {
  id: {
    type: FieldType.UUIDField,
    primary_key: true,
    readonly: true,
    verbose_name: "ID",
  },
  title: { type: FieldType.CharField, verbose_name: "Title", default: "" },
  is_published: {
    type: FieldType.BooleanField,
    verbose_name: "Published",
    default: false,
  },
};

function makeModel(edit: Partial<Model["admin"]["edit"]> = {}): Model {
  return {
    label: "testapp.article",
    verbose_name: "article",
    verbose_name_plural: "articles",
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
                fields: ["title", "is_published"].map((name) => ({
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
                })),
              },
            ],
          },
        ],
        sidebar: [],
        readonly_fields: [],
        prepopulated_fields: {},
        inlines: [],
        ...edit,
      },
      permissions: {
        add_permission: true,
        change_permission: true,
        delete_permission: true,
        view_permission: true,
      },
    },
    fields,
  } as Model;
}

const adminInfo = {
  formats: {},
  widgets: {
    [FieldType.CharField]: { name: FieldWidget.InputWidget },
    [FieldType.BooleanField]: { name: FieldWidget.CheckboxWidget },
  },
  settings: {
    created_at_attr: "created_at",
    created_by_attr: "created_by",
    edited_at_attr: "edited_at",
    edited_by_attr: "edited_by",
    recovery_max_age: 7,
  },
};

function discover(model: Model) {
  return {
    data: {
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
    },
  };
}

function renderEditor(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter([{ path: "/", element: ui }]);

  return render(
    <QueryClientProvider client={queryClient}>
      <ConfirmDialogProvider>
        <RouterProvider router={router} />
      </ConfirmDialogProvider>
    </QueryClientProvider>,
  );
}

function serve(object: Record<string, unknown> | null) {
  httpMock.get.mockImplementation((url: string) => {
    if (url === "/me") {
      return Promise.resolve({ data: { id: 7, username: "editor" } });
    }
    if (url.endsWith("/activity")) {
      return Promise.resolve({
        data: [
          {
            id: 1,
            action_flag: 2,
            action_time: new Date().toISOString(),
            user: { __str__: "Maya" },
          },
        ],
      });
    }
    return Promise.resolve({ data: object ?? {} });
  });
}

describe("Editor recovery", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
    useAdminInfoMock.mockReturnValue({ data: adminInfo });
    useDiscoverMock.mockReturnValue(discover(makeModel()));
  });

  it("keeps unsaved changes with the value they started from", async () => {
    serve({ id: "abc", title: "Old title", is_published: false });

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    const user = userEvent.setup();
    const title = await screen.findByDisplayValue("Old title");
    await user.clear(title);
    await user.type(title, "New title");
    fireEvent(window, new Event("pagehide"));

    await waitFor(() =>
      expect(readKept(KEY)?.fields).toEqual({
        title: { value: "New title", base: "Old title" },
      }),
    );
  });

  it("offers kept changes back and restores them as unsaved changes", async () => {
    serve({ id: "abc", title: "Old title", is_published: false });
    writeKept(KEY, kept({ title: { value: "Kept title", base: "Old title" } }));

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    expect(await screen.findByText("recovery.title")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Old title")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "recovery.restore" }),
    );

    expect(screen.getByDisplayValue("Kept title")).toBeInTheDocument();
    expect(screen.queryByTestId("recovery-banner")).not.toBeInTheDocument();
    expect(screen.getByText("editor.unsaved_changes")).toBeInTheDocument();
  });

  it("keeps the saved value of a field someone else changed since", async () => {
    serve({ id: "abc", title: "Their title", is_published: false });
    writeKept(
      KEY,
      kept({
        title: { value: "My title", base: "Old title" },
        is_published: { value: true, base: false },
      }),
    );

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    expect(
      await screen.findByText("recovery.clash_title_by"),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "recovery.restore" }),
    );

    expect(screen.getByDisplayValue("Their title")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeChecked();
    // The clash stays on offer in Compare.
    expect(screen.getByText("recovery.restored_title")).toBeInTheDocument();
  });

  it("restores a clash when the editor picks theirs in Compare", async () => {
    serve({ id: "abc", title: "Their title", is_published: false });
    writeKept(KEY, kept({ title: { value: "My title", base: "Old title" } }));

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "recovery.compare" }),
    );
    await user.click(screen.getByRole("radio", { name: "recovery.use_mine" }));
    await user.click(
      screen.getByRole("button", { name: "recovery.restore_count" }),
    );

    expect(screen.getByDisplayValue("My title")).toBeInTheDocument();
  });

  it("forgets kept changes on Discard", async () => {
    serve({ id: "abc", title: "Old title", is_published: false });
    writeKept(KEY, kept({ title: { value: "Kept title", base: "Old title" } }));

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    await userEvent.click(
      await screen.findByRole("button", { name: "recovery.discard" }),
    );

    expect(screen.queryByTestId("recovery-banner")).not.toBeInTheDocument();
    expect(readKept(KEY)).toBeNull();
    expect(screen.getByDisplayValue("Old title")).toBeInTheDocument();
  });

  it("forgets kept changes once saved", async () => {
    serve({ id: "abc", title: "Old title", is_published: false });
    httpMock.put.mockResolvedValue({
      data: { id: "abc", title: "New title", is_published: false },
    });

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    const user = userEvent.setup();
    const title = await screen.findByDisplayValue("Old title");
    await user.type(title, "!");
    fireEvent(window, new Event("pagehide"));
    await waitFor(() => expect(readKept(KEY)).not.toBeNull());

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(httpMock.put).toHaveBeenCalled());
    await waitFor(() => expect(readKept(KEY)).toBeNull());
  });

  it("offers an unfinished create form", async () => {
    serve(null);
    writeKept(NEW_KEY, kept({ title: { value: "Draft title", base: "" } }));

    renderEditor(<Editor modelLabel="testapp.article" onClose={vi.fn()} />);

    expect(
      await screen.findByText("recovery.create_title"),
    ).toBeInTheDocument();
  });

  it("does nothing for a studio that opts out", async () => {
    useDiscoverMock.mockReturnValue(
      discover(makeModel({ recover_changes: false })),
    );
    serve({ id: "abc", title: "Old title", is_published: false });
    writeKept(KEY, kept({ title: { value: "Kept title", base: "Old title" } }));

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    const user = userEvent.setup();
    const title = await screen.findByDisplayValue("Old title");
    await user.type(title, "!");
    fireEvent(window, new Event("pagehide"));

    expect(screen.queryByTestId("recovery-banner")).not.toBeInTheDocument();
    expect(readKept(KEY)?.fields.title.value).toBe("Kept title");
  });

  it("never keeps excluded fields", async () => {
    useDiscoverMock.mockReturnValue(
      discover(makeModel({ recover_changes_exclude: ["title"] })),
    );
    serve({ id: "abc", title: "Old title", is_published: false });

    renderEditor(
      <Editor modelLabel="testapp.article" id="abc" onClose={vi.fn()} />,
    );

    const user = userEvent.setup();
    await user.type(await screen.findByDisplayValue("Old title"), "!");
    await user.click(screen.getByRole("checkbox"));
    fireEvent(window, new Event("pagehide"));

    await waitFor(() =>
      expect(readKept(KEY)?.fields).toEqual({
        is_published: { value: true, base: false },
      }),
    );
  });
});
