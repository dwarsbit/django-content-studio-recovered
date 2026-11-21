import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { type ReactNode, useEffect } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { Header } from "@/components/content-editor/header";
import { FollowButton } from "@/components/notifications/follow-button";
import { Dialog } from "@/components/ui/dialog";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Model, Resource } from "@/types";

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }),
}));

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: { settings: { edited_at_attr: "edited_at" } } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const follow = vi.hoisted(() => ({ following: false }));

vi.mock("@/hooks/use-notifications", () => ({
  useFollow: () => ({
    data: { following: follow.following, creator: false },
    mutation: { isPending: false },
    setFollowing: vi.fn(),
  }),
}));

const model = {
  label: "testapp.article",
  verbose_name: "Article",
  verbose_name_plural: "Articles",
  admin: { is_singleton: false, icon: null, edit: { header: [] }, list: {} },
  fields: {},
} as unknown as Model;

const resource = {
  id: "7",
  __str__: "Hello",
  __view_on_site__: "/blog/hello/",
  edited_at: "2026-01-01T10:00:00Z",
} as unknown as Resource;

function Form({ dirty, children }: { dirty: boolean; children: ReactNode }) {
  const form = useForm({ defaultValues: { title: "Hello" } });

  useEffect(() => {
    if (dirty) {
      form.setValue("title", "Hello again", { shouldDirty: true });
    }
  }, [dirty, form]);

  return <FormProvider {...form}>{children}</FormProvider>;
}

function renderHeader({
  dirty = false,
  keptAt = null,
}: { dirty?: boolean; keptAt?: number | null } = {}) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ConfirmDialogProvider>
        <Dialog>
          <Form dirty={dirty}>
            <Header
              model={model}
              resource={resource}
              resourcePath="/content/testapp.article"
              isSaving={false}
              keptAt={keptAt}
              onSave={async () => {}}
            />
          </Form>
        </Dialog>
      </ConfirmDialogProvider>
    </QueryClientProvider>,
  );
}

describe("The edit header's status", () => {
  it("says when the object was last edited", () => {
    renderHeader();

    expect(screen.getByTestId("edit-status")).toHaveTextContent(
      "editor.last_edited",
    );
  });

  it("says there are unsaved changes instead", async () => {
    renderHeader({ dirty: true });

    const status = await screen.findByText("editor.unsaved_changes");

    expect(screen.getByTestId("edit-status")).toContainElement(status);
    expect(screen.queryByText(/editor.last_edited/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("changes-kept")).not.toBeInTheDocument();
  });

  it("adds that the changes are kept, in words", async () => {
    renderHeader({ dirty: true, keptAt: Date.now() });

    expect(await screen.findByTestId("changes-kept")).toHaveTextContent(
      "recovery.kept_short",
    );
  });

  it("sits next to the title, not among the actions", () => {
    renderHeader();

    const save = screen.getByRole("button", { name: "common.save" });
    const actions = save.parentElement!;

    expect(
      within(actions).queryByTestId("edit-status"),
    ).not.toBeInTheDocument();
    expect(
      within(actions).getByRole("link", { name: "editor.view_on_site" }),
    ).toBeInTheDocument();
  });
});

describe("The Follow button", () => {
  function renderFollow() {
    render(
      <TooltipProvider>
        <FollowButton model={model} id="7" name="Hello" />
      </TooltipProvider>,
    );
  }

  it("is an icon button named Follow", () => {
    follow.following = false;
    renderFollow();

    expect(
      screen.getByRole("button", { name: "notifications.follow.follow" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("is pressed and named Following while following", () => {
    follow.following = true;
    renderFollow();

    expect(
      screen.getByRole("button", { name: "notifications.follow.following" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});
