import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmailActivityPage } from "@/pages/(studio)/email-activity/page";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const useDiscoverMock = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-discover", () => ({ useDiscover: useDiscoverMock }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    i18n: { language: "en" },
  }),
}));

const now = new Date().toISOString();

function email(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    from_email: "noreply@example.com",
    to: ["sam@example.com"],
    cc: [],
    bcc: [],
    reply_to: [],
    subject: "You are invited",
    kind: "invite",
    kind_label: "Invite",
    status: "sent",
    error: null,
    backend: "SMTP · smtp.example.com:587",
    message_id: "<1@example.com>",
    attachments: [],
    size: 2048,
    sent_by: null,
    created_at: now,
    finished_at: now,
    duration: 420,
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}) {
  return {
    emails: [
      email(),
      email({
        id: 2,
        subject: "Weekly summary",
        kind: "",
        kind_label: "Other",
        status: "failed",
        to: ["finance@example.com", "ops@example.com", "kim@example.com"],
        attachments: [
          { name: "summary.pdf", type: "application/pdf", size: 1 },
        ],
        error: "SMTPRecipientsRefused: 550 User unknown",
      }),
    ],
    total: 60,
    offset: 0,
    limit: 50,
    counts: { all: 60, sent: 58, failed: 2 },
    kinds: [
      { value: "invite", label: "Invite" },
      { value: "", label: "Other" },
    ],
    summary: {
      backend: "SMTP · smtp.example.com:587",
      default_backend:
        "content_studio.contrib.email_activity.backends.EmailBackend",
      sent: 42,
      failed: 2,
      keep_days: 30,
      logging: true,
      masked: false,
    },
    your_email: "root@example.com",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <EmailActivityPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EmailActivityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDiscoverMock.mockReturnValue({
      data: { email_activity: { enabled: true }, status: { enabled: true } },
    });
    httpMock.get.mockResolvedValue({ data: page() });
  });

  it("lists the sent emails with the facts", async () => {
    renderPage();

    expect(await screen.findByText("You are invited")).toBeVisible();
    expect(screen.getAllByText("SMTP · smtp.example.com:587")[0]).toBeVisible();
    expect(
      screen.getByText('email_activity.failed_count {"count":2}'),
    ).toBeVisible();
    expect(
      screen.getByText('email_activity.keep_days {"count":30}'),
    ).toBeVisible();

    const rows = screen.getAllByRole("listitem");

    expect(rows[0]).toHaveAttribute("data-status", "sent");
    expect(rows[1]).toHaveAttribute("data-status", "failed");
    expect(rows[1]).toHaveTextContent(
      "SMTPRecipientsRefused: 550 User unknown",
    );
    expect(rows[1]).toHaveTextContent('email_activity.more {"count":2}');
    expect(rows[1]).toHaveTextContent("summary.pdf");
    expect(
      screen.getByRole("link", { name: "email_activity.back" }),
    ).toHaveAttribute("href", "/status");
  });

  it("filters by status and loads more", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", {
        name: /email_activity\.list\.failed/,
      }),
    );

    await waitFor(() =>
      expect(httpMock.get).toHaveBeenLastCalledWith("/email-activity", {
        params: { status: "failed", q: undefined, offset: 0 },
      }),
    );

    await user.click(
      await screen.findByRole("button", {
        name: "email_activity.list.load_more",
      }),
    );

    await waitFor(() =>
      expect(httpMock.get).toHaveBeenLastCalledWith("/email-activity", {
        params: { status: "failed", q: undefined, offset: 2 },
      }),
    );
  });

  it("opens an email's details", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Weekly summary"));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "SMTPRecipientsRefused",
    );
    expect(dialog).toHaveTextContent(
      "finance@example.com, ops@example.com, kim@example.com",
    );
    expect(dialog).toHaveTextContent("<1@example.com>");
    expect(dialog).toHaveTextContent("email_activity.details.no_body");
  });

  it("sends a test email to your own address", async () => {
    const user = userEvent.setup();
    httpMock.post.mockResolvedValue({
      data: { detail: "Test email sent to root@example.com." },
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "email_activity.send_test" }),
    );

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("email_activity.test.to")).toHaveValue(
      "root@example.com",
    );

    await user.click(
      within(dialog).getByRole("button", { name: "email_activity.send_test" }),
    );

    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith(
        "Test email sent to root@example.com.",
      ),
    );
    expect(httpMock.post).toHaveBeenCalledWith("/email-activity/test", {
      to: "root@example.com",
    });
  });

  it("shows why a test email failed in the dialog", async () => {
    const user = userEvent.setup();
    httpMock.post.mockRejectedValue({
      response: { data: { detail: "ConnectionRefusedError: refused" } },
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "email_activity.send_test" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "email_activity.send_test" }),
    );

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "ConnectionRefusedError: refused",
    );
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it("explains how to set up logging", async () => {
    httpMock.get.mockResolvedValue({
      data: page({
        emails: [],
        total: 0,
        counts: { all: 0, sent: 0, failed: 0 },
        summary: {
          ...page().summary,
          backend: "Console",
          default_backend: "django.core.mail.backends.console.EmailBackend",
          logging: false,
        },
      }),
    });
    renderPage();

    expect(
      await screen.findByText("email_activity.not_set_up_title"),
    ).toBeVisible();
    expect(
      screen.getByText(
        /"EMAIL_DELIVERY_BACKEND": "django\.core\.mail\.backends\.console\.EmailBackend"/,
      ),
    ).toBeVisible();
    expect(screen.queryByText("email_activity.list.title")).toBeNull();
  });

  it("is unavailable without permission", async () => {
    useDiscoverMock.mockReturnValue({
      data: { email_activity: { enabled: false } },
    });
    renderPage();

    expect(
      await screen.findByText("email_activity.unavailable_title"),
    ).toBeVisible();
    expect(httpMock.get).not.toHaveBeenCalled();
  });
});
