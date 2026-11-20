import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Form } from "@/components/ui/form";
import { ForeignKeyWidget } from "@/components/widgets/foreign-key-widget";
import { ManyToManyWidget } from "@/components/widgets/many-to-many-widget";
import type { Model, Permissions, Resource } from "@/types";

const httpMock = vi.hoisted(() => ({ post: vi.fn() }));
const discoverMock = vi.hoisted(() => ({ models: [] as unknown[] }));
const toastMock = vi.hoisted(() => ({ warning: vi.fn(), error: vi.fn() }));

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => httpMock,
}));

vi.mock("@/hooks/use-discover", () => ({
  useDiscover: () => ({ data: discoverMock }),
}));

vi.mock("sonner", () => ({ toast: toastMock }));

// The related studio's form is the Editor, tested on its own: this one
// shows what it was opened with and saves "Night trains" (id 9).
vi.mock("@/components/content-editor/editor", () => ({
  Editor: ({
    id,
    prefill,
    readOnly,
    onSave,
  }: {
    id?: string;
    prefill?: Record<string, unknown>;
    readOnly?: boolean;
    onSave?: (saved: Resource) => void;
  }) => (
    <div>
      <div>editor id: {id ?? "new"}</div>
      <div>editor prefill: {JSON.stringify(prefill ?? {})}</div>
      <div>editor read-only: {String(!!readOnly)}</div>
      <button
        type="button"
        onClick={() => onSave?.({ id: "9", __str__: "Night trains" })}
      >
        editor save
      </button>
    </div>
  ),
}));

const ALL: Permissions = {
  add_permission: true,
  change_permission: true,
  delete_permission: true,
  view_permission: true,
};

function makeModel(
  label: string,
  fields: Model["fields"],
  permissions: Permissions = ALL,
): Model {
  return {
    label,
    verbose_name: label.split(".")[1],
    verbose_name_plural: `${label.split(".")[1]}s`,
    tenant_field: null,
    admin: {
      is_singleton: false,
      icon: null,
      list: {
        per_page: 20,
        description: "",
        display: [],
        search: true,
        search_field: "name",
        filter: [],
        sortable_by: null,
        actions: [],
      },
      edit: { main: [], sidebar: [], inlines: [] },
      permissions,
    },
    fields,
  };
}

const ARTICLE = makeModel("testapp.article", {
  author: {
    type: "ForeignKey",
    required: false,
    related_model: "testapp.category",
  } as unknown as Model["fields"][string],
  categories: {
    type: "ManyToManyField",
    required: false,
    related_model: "testapp.category",
  } as unknown as Model["fields"][string],
});

function registerCategory(permissions: Permissions = ALL) {
  discoverMock.models = [
    ARTICLE,
    makeModel("testapp.category", {}, permissions),
  ];
}

// The relations endpoint: the picker's options, or the one object asked
// for by pk (null: outside what the picker offers).
function relations(
  lookup: Resource | null = { id: "9", __str__: "Night trains", icon: "tag" },
) {
  httpMock.post.mockImplementation(
    async (_url: string, body: { pk?: unknown }) => ({
      data: body.pk !== undefined ? (lookup ? [lookup] : []) : [],
    }),
  );
}

function renderWidget(widget: React.ReactNode) {
  function Harness() {
    const form = useForm();

    return (
      <QueryClientProvider client={new QueryClient()}>
        <Form {...form}>{widget}</Form>
      </QueryClientProvider>
    );
  }

  render(<Harness />);
}

beforeEach(() => {
  httpMock.post.mockReset();
  toastMock.warning.mockReset();
  registerCategory();
  relations();
});

describe("Creating from a foreign key picker", () => {
  it("creates an object from the typed text and chooses it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={null}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button"));
    await user.type(
      screen.getByPlaceholderText("common.search"),
      "Night trains",
    );
    await user.click(
      await screen.findByText("widgets.relation_widget.create_named"),
    );

    expect(screen.getByText("editor id: new")).toBeInTheDocument();
    expect(
      screen.getByText('editor prefill: {"name":"Night trains"}'),
    ).toBeInTheDocument();

    await user.click(screen.getByText("editor save"));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        id: "9",
        __str__: "Night trains",
        icon: "tag",
      }),
    );
    expect(httpMock.post).toHaveBeenLastCalledWith(
      "/content/testapp.article/relations/author",
      expect.objectContaining({ pk: "9", search: "" }),
    );
  });

  it("offers New without typed text, with nothing prefilled", async () => {
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={null}
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button"));
    await user.click(await screen.findByText("widgets.relation_widget.create"));

    expect(screen.getByText("editor prefill: {}")).toBeInTheDocument();
  });

  it("warns instead of choosing an object the picker does not offer", async () => {
    relations(null);
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={null}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button"));
    await user.click(await screen.findByText("widgets.relation_widget.create"));
    await user.click(screen.getByText("editor save"));

    await waitFor(() =>
      expect(toastMock.warning).toHaveBeenCalledWith(
        "widgets.relation_widget.created_not_offered",
      ),
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  it("offers no New without add permission", async () => {
    registerCategory({ ...ALL, add_permission: false });
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={null}
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button"));

    await screen.findByText("widgets.relation_widget.no_results");
    expect(
      screen.queryByText("widgets.relation_widget.create"),
    ).not.toBeInTheDocument();
  });

  it("offers no New for a related model without a studio", async () => {
    discoverMock.models = [ARTICLE];
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={null}
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button"));

    await screen.findByText("widgets.relation_widget.no_results");
    expect(
      screen.queryByText("widgets.relation_widget.create"),
    ).not.toBeInTheDocument();
  });

  it("offers neither New nor the pencil with allow_create=False", async () => {
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={{ id: "1", __str__: "Travel" }}
        onChange={vi.fn()}
        options={{ allow_create: false }}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "widgets.relation_widget.edit" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByText("Travel"));

    await screen.findAllByText("Travel");
    expect(
      screen.queryByText("widgets.relation_widget.create"),
    ).not.toBeInTheDocument();
  });
});

describe("Editing the chosen foreign key", () => {
  it("opens the chosen object and takes its new name", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={{ id: "9", __str__: "Night train" }}
        onChange={onChange}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "widgets.relation_widget.edit" }),
    );

    expect(screen.getByText("editor id: 9")).toBeInTheDocument();
    expect(screen.getByText("editor read-only: false")).toBeInTheDocument();

    await user.click(screen.getByText("editor save"));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        id: "9",
        __str__: "Night trains",
        icon: "tag",
      }),
    );
  });

  it("opens read-only without change permission", async () => {
    registerCategory({
      ...ALL,
      add_permission: false,
      change_permission: false,
    });
    const user = userEvent.setup();
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={{ id: "9", __str__: "Night train" }}
        onChange={vi.fn()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "widgets.relation_widget.edit" }),
    );

    expect(screen.getByText("editor read-only: true")).toBeInTheDocument();
  });

  it("shows no pencil without view permission", () => {
    registerCategory({ ...ALL, view_permission: false });
    renderWidget(
      <ForeignKeyWidget
        name="author"
        model={ARTICLE}
        value={{ id: "9", __str__: "Night train" }}
        onChange={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "widgets.relation_widget.edit" }),
    ).not.toBeInTheDocument();
  });
});

describe("Many-to-many pickers", () => {
  it("adds a created object to the chosen ones", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWidget(
      <ManyToManyWidget
        name="categories"
        model={ARTICLE}
        value={[{ id: "1", __str__: "Design" }]}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("combobox"));
    await user.type(
      screen.getByPlaceholderText("common.search"),
      "Night trains",
    );
    await user.click(
      await screen.findByText("widgets.relation_widget.create_named"),
    );
    await user.click(screen.getByText("editor save"));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith([
        { id: "1", __str__: "Design" },
        { id: "9", __str__: "Night trains", icon: "tag" },
      ]),
    );
  });

  it("edits a chosen object from its badge, keeping its place", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWidget(
      <ManyToManyWidget
        name="categories"
        model={ARTICLE}
        value={[
          { id: "9", __str__: "Night train" },
          { id: "1", __str__: "Design" },
        ]}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByText("Night train"));

    expect(screen.getByText("editor id: 9")).toBeInTheDocument();

    await user.click(screen.getByText("editor save"));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith([
        { id: "9", __str__: "Night trains", icon: "tag" },
        { id: "1", __str__: "Design" },
      ]),
    );
  });
});
