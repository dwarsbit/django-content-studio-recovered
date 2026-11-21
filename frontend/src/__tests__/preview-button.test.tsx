import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PreviewButton } from "@/components/content-editor/preview-button";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Resource } from "@/types";

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/hooks/use-http", () => ({ useHttp: () => http }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options?.name ? `${key}:${options.name}` : key,
  }),
}));

function resource(preview: Resource["__preview__"]) {
  return {
    id: "7",
    __str__: "Hello",
    __view_on_site__: "/blog/hello/",
    __preview__: preview,
  } as Resource;
}

function renderButton(
  value: Resource,
  { isDirty = false, onSave = vi.fn(async () => true) } = {},
) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <PreviewButton
          resource={value}
          resourcePath="/content/testapp.article"
          viewOnSiteUrl="/blog/hello/"
          isDirty={isDirty}
          onSave={onSave}
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );

  return { onSave };
}

async function openMenu() {
  await userEvent.click(screen.getByRole("button", { name: "preview.menu" }));
}

describe("The Preview button", () => {
  beforeEach(() => {
    http.get.mockReset();
    http.post.mockReset();
    http.delete.mockReset();
  });

  it("is a plain View on site link for live content", async () => {
    renderButton(resource({ live: true, can_share: false }));

    const link = screen.getByRole("link", { name: "editor.view_on_site" });
    expect(link).toHaveAttribute("href", "/blog/hello/");

    await openMenu();
    expect(
      screen.getByRole("menuitem", { name: "preview.copy_link" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("menuitem", { name: /preview.share/ }),
    ).not.toBeInTheDocument();
  });

  it("is View on site for a studio without previews", () => {
    renderButton(resource(null));

    expect(
      screen.getByRole("link", { name: "editor.view_on_site" }),
    ).toBeInTheDocument();
  });

  it("opens a draft with a preview link from the server", async () => {
    const tab = { opener: {}, location: { href: "" }, close: vi.fn() };
    const open = vi.spyOn(window, "open").mockReturnValue(tab as never);
    http.post.mockResolvedValue({ data: { url: "/blog/hello/?preview=abc" } });
    renderButton(resource({ live: false, can_share: false }));

    await userEvent.click(
      screen.getByRole("button", { name: "preview.preview_draft" }),
    );

    await waitFor(() =>
      expect(tab.location.href).toBe(
        `${window.location.origin}/blog/hello/?preview=abc`,
      ),
    );
    expect(tab.opener).toBeNull();
    expect(http.post).toHaveBeenCalledWith(
      "/content/testapp.article/7/preview",
      { language: null },
    );
    open.mockRestore();
  });

  it("offers sharing only with the share permission", async () => {
    renderButton(resource({ live: false, can_share: false }));
    await openMenu();

    expect(
      screen.getByRole("menuitem", { name: /preview.copy_preview_link/ }),
    ).toBeVisible();
    expect(
      screen.queryByRole("menuitem", { name: "preview.share" }),
    ).not.toBeInTheDocument();
  });

  it("offers Save and preview with unsaved changes", async () => {
    const tab = { opener: {}, location: { href: "" }, close: vi.fn() };
    const open = vi.spyOn(window, "open").mockReturnValue(tab as never);
    http.post.mockResolvedValue({ data: { url: "/blog/hello/?preview=abc" } });
    const { onSave } = renderButton(
      resource({ live: false, can_share: true }),
      {
        isDirty: true,
      },
    );
    await openMenu();

    await userEvent.click(
      screen.getByRole("menuitem", { name: "preview.save_and_preview" }),
    );

    await waitFor(() => expect(tab.location.href).toContain("preview=abc"));
    expect(onSave).toHaveBeenCalled();
    open.mockRestore();
  });

  it("shares a draft link and shows it once", async () => {
    http.get.mockResolvedValue({
      data: {
        links: [
          {
            id: 1,
            note: "Photo desk",
            language: null,
            created_by: "Maya",
            created_at: "2026-11-20T10:00:00Z",
            expires_at: null,
            opens: 0,
            last_opened_at: null,
          },
        ],
      },
    });
    http.post.mockResolvedValue({
      data: {
        created: {
          id: 2,
          note: "Client",
          language: null,
          created_by: "Alex",
          created_at: "2026-11-21T10:00:00Z",
          expires_at: "2026-11-28T10:00:00Z",
          opens: 0,
          last_opened_at: null,
          url: "/blog/hello/?preview=key",
        },
        links: [],
      },
    });
    renderButton(resource({ live: false, can_share: true }));
    await openMenu();
    await userEvent.click(
      screen.getByRole("menuitem", { name: "preview.share" }),
    );

    expect(await screen.findByText("Photo desk")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/preview.note/), "Client");
    await userEvent.click(
      screen.getByRole("button", { name: "preview.create" }),
    );

    const input = await screen.findByLabelText("preview.new_link");
    expect(input).toHaveValue(
      `${window.location.origin}/blog/hello/?preview=key`,
    );
    const [path, body] = http.post.mock.calls[0];
    expect(path).toBe("/content/testapp.article/7/preview-links");
    expect(body.note).toBe("Client");
    expect(body.expires_at).toBeTruthy();
  });

  it("revokes a link", async () => {
    http.get.mockResolvedValue({
      data: {
        links: [
          {
            id: 1,
            note: "Photo desk",
            language: null,
            created_by: "Maya",
            created_at: "2026-11-20T10:00:00Z",
            expires_at: null,
            opens: 2,
            last_opened_at: null,
          },
        ],
      },
    });
    http.delete.mockResolvedValue({});
    renderButton(resource({ live: false, can_share: true }));
    await openMenu();
    await userEvent.click(
      screen.getByRole("menuitem", { name: "preview.share" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "preview.revoke" }),
    );

    expect(http.delete).toHaveBeenCalledWith(
      "/content/testapp.article/7/preview-links/1",
    );
  });
});
