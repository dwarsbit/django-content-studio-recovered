import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BackupsPage } from "@/pages/(studio)/backups/page";

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));
const useDiscoverMock = vi.hoisted(() => vi.fn());
const saveFileMock = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/lib/download", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/download")>()),
  saveFile: saveFileMock,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    i18n: { language: "en" },
  }),
}));

const now = new Date().toISOString();

function backup(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    database: "default",
    status: "done",
    trigger: "scheduled",
    file: "content_studio/backups/default/2026-11-20T030000Z.json.gz",
    name: "2026-11-20T030000Z.json.gz",
    size: 3_565_158,
    error: null,
    created_by: null,
    created_at: now,
    started_at: now,
    finished_at: now,
    duration: 12,
    ...overrides,
  };
}

function list(overrides: Record<string, unknown> = {}) {
  return {
    backups: [
      backup(),
      backup({
        id: 2,
        status: "failed",
        file: "",
        name: "",
        size: null,
        error: "OSError: bucket gone",
        trigger: "manual",
        created_by: "root",
      }),
    ],
    schedule: "Daily at 03:00",
    next_run_at: now,
    keep: 14,
    databases: ["default"],
    storage: "S3Storage",
    folder: "content_studio/backups",
    ...overrides,
  };
}

const restoreInfo = {
  enabled: true,
  databases: [{ alias: "default", name: "app.sqlite3" }],
  max_upload_size: 1024 ** 3,
  password_required: true,
  suffixes: [".json", ".json.gz", ".json.bz2", ".json.xz", ".json.lzma"],
};

function preview(overrides: Record<string, unknown> = {}) {
  return {
    database: "default",
    database_name: "app.sqlite3",
    manifest: true,
    created_at: now,
    content_studio: "1.17.0",
    django: "6.0",
    engine: "sqlite",
    rows: 1234,
    models: [
      { label: "blog.Post", count: 1000 },
      { label: "auth.User", count: 234 },
    ],
    skipped: 0,
    remapped: 0,
    unknown_models: [],
    migrations: {
      checked: true,
      match: true,
      applied: 42,
      missing: [],
      extra: [],
    },
    ...overrides,
  };
}

function restore(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    database: "default",
    status: "done",
    source: "backup",
    backup: 1,
    name: "2026-11-20T030000Z.json.gz",
    size: 3_565_158,
    rows: 1234,
    error: null,
    safety_backup: "2026-11-20T140000Z.json.gz",
    created_by: "root",
    created_at: now,
    started_at: now,
    finished_at: now,
    duration: 8,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <BackupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BackupsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDiscoverMock.mockReturnValue({
      data: { backups: { enabled: true }, status: { enabled: true } },
    });
    httpMock.get.mockImplementation((url: string) =>
      url === "/backups"
        ? Promise.resolve({ data: list() })
        : Promise.reject(new Error(url)),
    );
  });

  it("lists the backups with their schedule and storage", async () => {
    renderPage();

    expect(
      await screen.findByText(/backups\.schedule_next .*Daily at 03:00/),
    ).toBeVisible();
    expect(screen.getByText('backups.keep {"count":14}')).toBeVisible();
    expect(
      screen.getByText("S3Storage · content_studio/backups"),
    ).toBeVisible();

    const rows = screen.getAllByRole("listitem");

    expect(rows[0]).toHaveAttribute("data-status", "done");
    expect(rows[0]).toHaveTextContent("3.4 MB");
    expect(rows[0]).toHaveTextContent("2026-11-20T030000Z.json.gz");
    expect(rows[1]).toHaveAttribute("data-status", "failed");
    expect(rows[1]).toHaveTextContent("OSError: bucket gone");
    expect(rows[1]).toHaveTextContent("backups.by");
    // Only a finished backup has a file to download.
    expect(
      screen.getAllByRole("button", { name: /backups\.download/ }),
    ).toHaveLength(1);
    expect(screen.getByRole("link", { name: "backups.back" })).toHaveAttribute(
      "href",
      "/status",
    );
  });

  it("downloads a backup", async () => {
    const user = userEvent.setup();
    const blob = new Blob(["x"]);
    httpMock.get.mockImplementation((url: string) =>
      url === "/backups"
        ? Promise.resolve({ data: list() })
        : Promise.resolve({
            data: blob,
            headers: {
              "content-disposition":
                'attachment; filename="2026-11-20T030000Z.json.gz"',
            },
          }),
    );
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: /backups\.download/ }),
    );

    await waitFor(() =>
      expect(saveFileMock).toHaveBeenCalledWith(
        blob,
        "2026-11-20T030000Z.json.gz",
      ),
    );
    expect(httpMock.get).toHaveBeenCalledWith("/backups/1/download", {
      responseType: "blob",
    });
  });

  it("backs up now", async () => {
    const user = userEvent.setup();
    httpMock.post.mockResolvedValue({ data: { backups: [] } });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: /backups\.back_up_now/ }),
    );

    expect(httpMock.post).toHaveBeenCalledWith("/backups");
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith("backups.started"),
    );
  });

  it("waits while a backup runs", async () => {
    httpMock.get.mockResolvedValue({
      data: list({
        backups: [backup({ status: "running", finished_at: null })],
      }),
    });
    renderPage();

    expect(
      await screen.findByRole("button", { name: /backups\.running/ }),
    ).toBeDisabled();
  });

  it("explains an empty list", async () => {
    httpMock.get.mockResolvedValue({
      data: list({ backups: [], schedule: null, next_run_at: null }),
    });
    renderPage();

    expect(await screen.findByText("backups.list.empty_title")).toBeVisible();
    expect(screen.getByText("backups.not_scheduled")).toBeVisible();
  });

  it("is unavailable without the permission", () => {
    useDiscoverMock.mockReturnValue({ data: { backups: { enabled: false } } });
    renderPage();

    expect(screen.getByText("backups.unavailable_title")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /backups\.back_up_now/ }),
    ).not.toBeInTheDocument();
  });

  describe("restore", () => {
    function withRestore(overrides: Record<string, unknown> = {}) {
      return list({ restore: restoreInfo, restores: [], ...overrides });
    }

    beforeEach(() => {
      httpMock.get.mockImplementation((url: string) =>
        url === "/backups"
          ? Promise.resolve({ data: withRestore() })
          : url === "/backups/1/inspect"
            ? Promise.resolve({ data: { preview: preview() } })
            : Promise.reject(new Error(url)),
      );
    });

    it("is not offered without the permission", async () => {
      httpMock.get.mockResolvedValue({
        data: list({ restore: { ...restoreInfo, enabled: false } }),
      });
      renderPage();

      await screen.findByRole("button", { name: /backups\.download/ });
      expect(
        screen.queryByRole("button", { name: /backups\.restore_item/ }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "backups.more_actions" }),
      ).not.toBeInTheDocument();
      expect(screen.getByText(/backups\.restore_hint/)).toBeVisible();
    });

    it("restores a listed backup", async () => {
      const user = userEvent.setup();
      httpMock.post.mockResolvedValue({ data: { restore: restore() } });
      renderPage();

      await user.click(
        await screen.findByRole("button", { name: /backups\.restore_item/ }),
      );

      const dialog = await screen.findByRole("dialog");
      expect(
        await within(dialog).findByText("backups.restore.migrations_match"),
      ).toBeVisible();
      expect(httpMock.get).toHaveBeenCalledWith("/backups/1/inspect");

      const submit = within(dialog).getByRole("button", {
        name: "backups.restore.submit",
      });
      expect(submit).toBeDisabled();
      expect(
        within(dialog).getByRole("checkbox", {
          name: "backups.restore.safety",
        }),
      ).toBeChecked();

      await user.type(
        within(dialog).getByLabelText(/backups\.restore\.confirm/),
        "app.sqlite3",
      );
      // The password is still missing.
      expect(submit).toBeDisabled();
      await user.type(
        within(dialog).getByLabelText("backups.restore.password"),
        "secret",
      );
      await user.click(submit);

      await waitFor(() =>
        expect(httpMock.post).toHaveBeenCalledWith("/backups/restore", {
          backup: 1,
          confirm: "app.sqlite3",
          password: "secret",
          safety_backup: true,
          ignore_migrations: false,
        }),
      );
      expect(toastMock.success).toHaveBeenCalledWith("backups.restore.started");
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
    });

    it("asks to restore anyway when migrations differ", async () => {
      const user = userEvent.setup();
      httpMock.get.mockImplementation((url: string) =>
        url === "/backups"
          ? Promise.resolve({
              data: withRestore({
                restore: { ...restoreInfo, password_required: false },
              }),
            })
          : Promise.resolve({
              data: {
                preview: preview({
                  migrations: {
                    checked: true,
                    match: false,
                    missing: ["blog.0005_tags"],
                    extra: [],
                  },
                }),
              },
            }),
      );
      httpMock.post.mockResolvedValue({ data: { restore: restore() } });
      renderPage();

      await user.click(
        await screen.findByRole("button", { name: /backups\.restore_item/ }),
      );

      const dialog = await screen.findByRole("dialog");
      expect(
        await within(dialog).findByText("backups.restore.migrations_differ"),
      ).toBeVisible();
      expect(within(dialog).getByText(/blog\.0005_tags/)).toBeVisible();
      expect(
        within(dialog).queryByLabelText("backups.restore.password"),
      ).not.toBeInTheDocument();

      await user.type(
        within(dialog).getByLabelText(/backups\.restore\.confirm/),
        "app.sqlite3",
      );
      const submit = within(dialog).getByRole("button", {
        name: "backups.restore.submit",
      });
      expect(submit).toBeDisabled();

      await user.click(
        within(dialog).getByRole("checkbox", {
          name: "backups.restore.anyway",
        }),
      );
      await user.click(
        within(dialog).getByRole("checkbox", {
          name: "backups.restore.safety",
        }),
      );
      await user.click(submit);

      await waitFor(() =>
        expect(httpMock.post).toHaveBeenCalledWith("/backups/restore", {
          backup: 1,
          confirm: "app.sqlite3",
          password: "",
          safety_backup: false,
          ignore_migrations: true,
        }),
      );
    });

    it("shows the server's errors by their field", async () => {
      const user = userEvent.setup();
      httpMock.post.mockRejectedValue({
        response: { status: 400, data: { password: ["Wrong password."] } },
      });
      renderPage();

      await user.click(
        await screen.findByRole("button", { name: /backups\.restore_item/ }),
      );

      const dialog = await screen.findByRole("dialog");
      await user.type(
        await within(dialog).findByLabelText(/backups\.restore\.confirm/),
        "app.sqlite3",
      );
      await user.type(
        within(dialog).getByLabelText("backups.restore.password"),
        "nope",
      );
      await user.click(
        within(dialog).getByRole("button", { name: "backups.restore.submit" }),
      );

      expect(await within(dialog).findByText("Wrong password.")).toBeVisible();
      expect(screen.getByRole("dialog")).toBeVisible();
    });

    it("uploads a file, shows what it holds and cancels it", async () => {
      const user = userEvent.setup();
      httpMock.post.mockResolvedValue({
        data: {
          upload: restore({
            id: 5,
            status: "pending",
            source: "upload",
            name: "dump.json.gz",
            size: 2048,
          }),
          preview: preview({
            manifest: false,
            created_at: null,
            content_studio: null,
            django: null,
            engine: null,
            skipped: 80,
            remapped: 12,
            migrations: {
              checked: false,
              match: false,
              missing: [],
              extra: [],
            },
          }),
        },
      });
      httpMock.delete.mockResolvedValue({});
      renderPage();

      await user.click(
        await screen.findByRole("button", { name: "backups.more_actions" }),
      );
      await user.click(
        await screen.findByRole("menuitem", {
          name: "backups.restore_from_file",
        }),
      );

      const dialog = await screen.findByRole("dialog");
      const file = new File(["[]"], "dump.json.gz", {
        type: "application/gzip",
      });
      await user.upload(within(dialog).getByTestId("restore-file-input"), file);

      expect(
        await within(dialog).findByText("backups.restore.no_manifest"),
      ).toBeVisible();
      expect(
        within(dialog).getByText("backups.restore.dumpdata"),
      ).toBeVisible();
      expect(
        within(dialog).getByText(/backups\.restore\.skipped/),
      ).toBeVisible();

      const [url, body] = httpMock.post.mock.calls[0] as [string, FormData];
      expect(url).toBe("/backups/uploads");
      expect((body.get("file") as File).name).toBe("dump.json.gz");

      await user.click(
        within(dialog).getByRole("button", { name: "backups.restore.cancel" }),
      );

      await waitFor(() =>
        expect(httpMock.delete).toHaveBeenCalledWith("/backups/uploads/5"),
      );
    });

    it("refuses a file it can't restore before uploading", async () => {
      const user = userEvent.setup({ applyAccept: false });
      renderPage();

      await user.click(
        await screen.findByRole("button", { name: "backups.more_actions" }),
      );
      await user.click(
        await screen.findByRole("menuitem", {
          name: "backups.restore_from_file",
        }),
      );

      const dialog = await screen.findByRole("dialog");
      await user.upload(
        within(dialog).getByTestId("restore-file-input"),
        new File(["x"], "dump.sql"),
      );

      expect(
        await within(dialog).findByText(/backups\.restore\.wrong_type/),
      ).toBeVisible();
      expect(httpMock.post).not.toHaveBeenCalled();
    });

    it("shows a restore that runs and the recent restores", async () => {
      httpMock.get.mockResolvedValue({
        data: withRestore({
          restores: [
            restore({ id: 8, status: "running", finished_at: null }),
            restore({ status: "failed", error: "IntegrityError" }),
          ],
        }),
      });
      renderPage();

      expect(await screen.findByText(/backups\.restoring /)).toBeVisible();
      expect(
        screen.getByRole("button", { name: /backups\.back_up_now/ }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: /backups\.restore_item/ }),
      ).toBeDisabled();
      expect(screen.getByText("backups.restores.title")).toBeVisible();
      expect(screen.getByText("IntegrityError")).toBeVisible();
    });

    it("loads everything again once a restore is done", async () => {
      const running = withRestore({
        restores: [restore({ status: "running", finished_at: null })],
      });
      const done = withRestore({ restores: [restore()] });
      httpMock.get
        .mockResolvedValueOnce({ data: running })
        .mockResolvedValue({ data: done });
      const client = new QueryClient();
      const invalidate = vi.spyOn(client, "invalidateQueries");
      render(
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <BackupsPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await screen.findByText(/backups\.restoring /);
      await client.refetchQueries({ queryKey: ["backups"] });

      await waitFor(() =>
        expect(toastMock.success).toHaveBeenCalledWith(
          expect.stringContaining("backups.restore.done"),
        ),
      );
      expect(invalidate).toHaveBeenCalledWith();
    });
  });
});
