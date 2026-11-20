import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StatusPage } from "@/pages/(studio)/status/page";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const useDiscoverMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
  }),
}));

const now = new Date().toISOString();

function service(overrides: Record<string, unknown>) {
  return {
    key: "content_studio.database",
    label: "Database",
    group: "Content Studio",
    icon: "ph-bold ph-database",
    status: "ok",
    detail: "PostgreSQL 17.2",
    message: "",
    duration: 3,
    ...overrides,
  };
}

const services = {
  checked_at: now,
  status: "degraded",
  services: [
    service({}),
    service({
      key: "content_studio.email",
      label: "Email",
      status: "unknown",
      detail: "Console backend",
    }),
    service({
      key: "shop.payments",
      label: "Payments",
      group: "Shop",
      icon: null,
      status: "degraded",
      detail: "Mollie",
      message: "Responding slowly.",
      duration: 2400,
    }),
  ],
};

const tasks = {
  connected: true,
  pending: [
    {
      key: null,
      title: "Import articles",
      source: "Magazine",
      status: "QUEUED",
      at: null,
      duration: null,
      error_message: null,
    },
  ],
  finished: [
    {
      key: "shop.tasks.sync_orders",
      title: "Sync orders",
      source: "Shop",
      status: "FAILURE",
      at: now,
      duration: 31,
      error_message: "The shop answered 503",
    },
  ],
  recurring: [
    {
      key: "backups.database",
      title: "Back up database",
      source: "Backups",
      schedule: "Every day at 02:00",
      next_run_at: now,
      last_run_at: now,
      last_status: "SUCCESS",
      error_message: null,
      overdue: true,
    },
  ],
  counts: { pending: 1, failed: 1 },
  errors: [],
};

function respond(overrides: Record<string, unknown> = {}) {
  const responses: Record<string, unknown> = {
    "/status": services,
    "/status/tasks": tasks,
    ...overrides,
  };

  httpMock.get.mockImplementation((url: string) =>
    url in responses
      ? Promise.resolve({ data: responses[url] })
      : Promise.reject(new Error(url)),
  );
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <StatusPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StatusPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDiscoverMock.mockReturnValue({ data: { status: { enabled: true } } });
    respond();
  });

  it("lists the services by group with their status", async () => {
    renderPage();

    const shop = await screen.findByRole("group", { name: "Shop" });
    const payments = within(shop).getByText("Payments").closest("li")!;

    expect(payments).toHaveAttribute("data-status", "degraded");
    expect(payments).toHaveTextContent("Mollie · 2.4 s");
    expect(payments).toHaveTextContent("Responding slowly.");
    expect(payments).toHaveTextContent("status.service_status.degraded");

    const core = screen.getByRole("group", { name: "Content Studio" });

    expect(within(core).getByText("PostgreSQL 17.2 · 3 ms")).toBeVisible();
    // A service that is not checked shows no time and is not counted.
    expect(within(core).getByText("Console backend")).toBeVisible();
    expect(
      screen.getByText('status.services.operational {"count":1,"total":2}'),
    ).toBeVisible();
  });

  it("sums up what needs attention", async () => {
    renderPage();

    expect(
      await screen.findByText('status.overview.degraded {"count":1}'),
    ).toBeVisible();
    await waitFor(() =>
      expect(
        screen.getByText(
          /Payments: Responding slowly\. status\.overview\.failed_tasks/,
        ),
      ).toBeVisible(),
    );
  });

  it("filters the recent tasks", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Import articles")).toBeVisible();
    expect(screen.getByText("The shop answered 503")).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: /status\.tasks\.filters\.pending/ }),
    );

    expect(screen.getByText("Import articles")).toBeVisible();
    expect(screen.queryByText("Sync orders")).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /status\.tasks\.filters\.finished/ }),
    );

    expect(screen.queryByText("Import articles")).not.toBeInTheDocument();
    expect(screen.getByText("Sync orders")).toBeVisible();
  });

  it("shows a recurring task past its time as due", async () => {
    renderPage();

    const row = (await screen.findByText("Back up database")).closest("li")!;

    expect(row).toHaveAttribute("data-overdue", "true");
    expect(row).toHaveTextContent("Every day at 02:00");
    expect(row).toHaveTextContent("status.recurring.due");
    expect(row).toHaveTextContent("status.recurring.succeeded");
  });

  it("explains that no task backend is connected", async () => {
    respond({
      "/status/tasks": {
        ...tasks,
        connected: false,
        pending: [],
        finished: [],
        recurring: [],
      },
    });
    renderPage();

    expect(
      await screen.findByText("status.tasks.disconnected_title"),
    ).toBeVisible();
    expect(
      screen.queryByText("status.recurring.title"),
    ).not.toBeInTheDocument();
  });

  it("checks again on Refresh", async () => {
    const user = userEvent.setup();
    httpMock.post.mockResolvedValue({
      data: { ...services, status: "ok", services: [service({})] },
    });
    renderPage();

    await screen.findByRole("group", { name: "Shop" });
    await user.click(screen.getByRole("button", { name: "status.refresh" }));

    expect(httpMock.post).toHaveBeenCalledWith("/status/refresh");
    expect(await screen.findByText("status.overview.ok")).toBeVisible();
    expect(
      screen.queryByRole("group", { name: "Shop" }),
    ).not.toBeInTheDocument();
  });

  it("says so when the page is not available", async () => {
    useDiscoverMock.mockReturnValue({ data: { status: { enabled: false } } });
    renderPage();

    expect(await screen.findByText("status.unavailable_title")).toBeVisible();
  });
});
