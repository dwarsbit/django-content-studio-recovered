import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImportDialog } from "@/components/import-dialog";
import { ListActionsMenu } from "@/pages/(studio)/content/[model]/_components/list-actions-menu";
import type { ImportConfig, ImportResult, Model } from "@/types";

const httpGetMock = vi.hoisted(() => vi.fn());
const httpPostMock = vi.hoisted(() => vi.fn());
const httpDeleteMock = vi.hoisted(() => vi.fn(async () => ({})));
const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  loading: vi.fn(() => "toast"),
}));

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({
    get: httpGetMock,
    post: httpPostMock,
    delete: httpDeleteMock,
  }),
}));

vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "number" in options ? `${key}:${options.number}` : key,
    i18n: { language: "en" },
  }),
}));

window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false);
window.HTMLElement.prototype.releasePointerCapture = vi.fn();
window.HTMLElement.prototype.setPointerCapture = vi.fn();

const config: ImportConfig = {
  formats: ["csv", "xlsx", "json"],
  template_formats: ["csv", "xlsx"],
  key: ["id"],
  columns: [
    { name: "id", label: "ID", lookup: null, required: false },
    { name: "title", label: "Title", lookup: null, required: true },
    { name: "tags", label: "Tags", lookup: "name", required: false },
  ],
  can_import: true,
  can_create: true,
  can_update: true,
};

const model = {
  label: "testapp.event",
  verbose_name: "event",
  verbose_name_plural: "events",
  admin: { list: { import: config } },
} as unknown as Model;

function result(overrides: Partial<ImportResult> = {}): ImportResult {
  return {
    preview: true,
    applied: false,
    total: 3,
    created: 1,
    updated: 1,
    unchanged: 0,
    failed: 1,
    failures: [
      {
        row: 4,
        errors: [
          {
            column: "title",
            field: "title",
            messages: ["This field may not be blank."],
          },
        ],
      },
    ],
    ignored_columns: ["notes"],
    errors: [],
    ...overrides,
  };
}

function renderDialog() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ImportDialog model={model} open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

async function pickFile() {
  const file = new File(["id,title\n"], "events.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByTestId("import-file-input"), file);
}

describe("ImportDialog", () => {
  afterEach(() => {
    vi.clearAllMocks();
    httpPostMock.mockReset();
  });

  it("lists the columns and offers the template", () => {
    renderDialog();

    expect(screen.getByText("title")).toBeInTheDocument();
    expect(screen.getByText("(import.by_lookup)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "export.xlsx" })).toBeVisible();
  });

  it("checks the file, then imports the valid rows", async () => {
    httpPostMock
      .mockResolvedValueOnce({ data: { result: result() } })
      .mockResolvedValueOnce({
        data: { result: result({ preview: false, applied: true }) },
      });

    renderDialog();
    await pickFile();

    expect(
      await screen.findByText("This field may not be blank."),
    ).toBeInTheDocument();
    expect(screen.getByText("import.row")).toBeInTheDocument();
    const preview = httpPostMock.mock.calls[0][1] as FormData;
    expect(preview.get("preview")).toBe("true");
    expect(httpPostMock.mock.calls[0][0]).toBe("/content/testapp.event/import");

    await userEvent.click(
      screen.getByRole("button", { name: "import.import_valid:2" }),
    );

    await waitFor(() => expect(toastMock.success).toHaveBeenCalled());
    const run = httpPostMock.mock.calls[1][1] as FormData;
    expect(run.get("preview")).toBe("false");
    expect(run.get("skip_errors")).toBe("true");
  });

  it("discards a background check that is cancelled", async () => {
    httpPostMock.mockResolvedValueOnce({
      data: { job: { id: "job-1", status: "done", result: result() } },
    });

    renderDialog();
    await pickFile();

    await screen.findByText("This field may not be blank.");
    await userEvent.click(
      screen.getByRole("button", { name: "common.cancel" }),
    );

    expect(httpDeleteMock).toHaveBeenCalledWith(
      "/content/testapp.event/import/job-1",
    );
  });

  it("shows why a file cannot be imported", async () => {
    httpPostMock.mockRejectedValueOnce({
      response: { data: { file: ["The file is empty."] } },
    });

    renderDialog();
    await pickFile();

    expect(await screen.findByText("The file is empty.")).toBeInTheDocument();
  });

  it("offers nothing to import when every row fails", async () => {
    httpPostMock.mockResolvedValueOnce({
      data: { result: result({ created: 0, updated: 0, failed: 3 }) },
    });

    renderDialog();
    await pickFile();

    expect(
      await screen.findByRole("button", { name: "import.nothing_valid" }),
    ).toBeDisabled();
  });
});

describe("ListActionsMenu", () => {
  it("offers import and both exports in submenus", async () => {
    const onImport = vi.fn();
    const onExportForImport = vi.fn();

    render(
      <ListActionsMenu
        exportFormats={["csv"]}
        onExport={vi.fn()}
        importFormats={["csv", "json"]}
        onExportForImport={onExportForImport}
        onImport={onImport}
      />,
    );

    await userEvent.click(
      screen.getByRole("button", { name: "list_view.more_actions" }),
    );
    expect(
      screen.getByRole("menuitem", { name: "import.from_file" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "export.button" }),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("menuitem", { name: "export.for_import" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "export.json" }),
    );

    expect(onExportForImport).toHaveBeenCalledWith("json");
  });

  it("is hidden when there is nothing to offer", () => {
    const { container } = render(
      <ListActionsMenu exportFormats={[]} onExport={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
