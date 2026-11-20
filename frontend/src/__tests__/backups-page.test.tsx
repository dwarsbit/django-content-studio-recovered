import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BackupsPage } from "@/pages/(studio)/backups/page";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
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
});
