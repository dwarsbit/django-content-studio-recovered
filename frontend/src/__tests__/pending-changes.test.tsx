import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { Header } from "@/components/content-editor/header";
import { PublishingFormat } from "@/components/publishing/publishing-badge";
import { PublishingCard } from "@/components/publishing/publishing-card";
import { PublishingProvider } from "@/components/publishing/publishing-controls";
import { Dialog } from "@/components/ui/dialog";
import type { Model, PublishingInfo, Resource } from "@/types";

const post = vi.fn();

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({ get: vi.fn(), post, delete: vi.fn() }),
}));

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: { settings: { edited_at_attr: "edited_at" } } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

const model = {
  label: "blog.article",
  verbose_name: "article",
  verbose_name_plural: "articles",
  admin: {
    is_singleton: false,
    icon: null,
    edit: { header: [], sidebar: [] },
    list: {
      publishing: { unpublish: true, can_publish: true, pending_changes: true },
    },
  },
  fields: {
    title: { type: "CharField", verbose_name: "title" },
    intro: { type: "TextField", verbose_name: "intro" },
  },
} as unknown as Model;

function article(
  info: Partial<PublishingInfo>,
  values: Record<string, unknown> = {},
): Resource {
  return {
    id: "7",
    __str__: "Hello",
    title: "Hello",
    ...values,
    __publishing__: {
      state: "published",
      has_pending: false,
      pending: null,
      published_at: null,
      unpublish_at: null,
      can_publish: true,
      ...info,
    },
  } as Resource;
}

function Form({ children }: { children: ReactNode }) {
  const form = useForm();

  return <FormProvider {...form}>{children}</FormProvider>;
}

function renderEditor(
  resource: Resource,
  { isDirty = false, save = vi.fn(async () => true), onChanged = vi.fn() } = {},
) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ConfirmDialogProvider>
        <Dialog>
          <Form>
            <PublishingProvider
              model={model}
              resource={resource}
              resourcePath="/content/blog.article"
              isDirty={isDirty}
              readOnly={false}
              save={save}
              onChanged={onChanged}
            >
              <Header
                model={model}
                resource={resource}
                resourcePath="/content/blog.article"
                isSaving={false}
                onSave={async () => {}}
              />
              <PublishingCard />
            </PublishingProvider>
          </Form>
        </Dialog>
      </ConfirmDialogProvider>
    </QueryClientProvider>,
  );

  return { save, onChanged };
}

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: { state: "published" } });
});

const pending = {
  has_pending: true,
  pending: {
    fields: ["title", "intro"],
    edited_by: "Maya",
    edited_at: new Date().toISOString(),
    live: { title: "Hello", intro: "Old intro" },
  },
};

describe("Unpublished changes", () => {
  it("keeps a plain Save for live content without changes", () => {
    renderEditor(article({}));

    expect(screen.getByRole("button", { name: "common.save" })).toBeVisible();
    expect(screen.queryByTestId("publish-button")).toBeNull();
    expect(screen.queryByTestId("pending-changes")).toBeNull();
  });

  it("offers Publish changes once the form has changes", () => {
    renderEditor(article({}), { isDirty: true });

    expect(screen.getByTestId("publish-button")).toHaveTextContent(
      "publishing.publish_changes",
    );
  });

  it("shows the unpublished changes in the header and the card", () => {
    renderEditor(article(pending, { title: "Hello again", intro: "New" }));

    expect(screen.getByTestId("edit-status-pending")).toHaveTextContent(
      "publishing.changes.title",
    );
    const card = screen.getByTestId("pending-changes");
    expect(card).toHaveTextContent("Title and Intro");
    expect(card).toHaveTextContent("publishing.changes.saved_by");
  });

  it("publishes the changes, saving unsaved ones first", async () => {
    const order: string[] = [];
    const save = vi.fn(async () => {
      order.push("save");
      return true;
    });
    post.mockImplementation(async (_url: string, data: { action: string }) => {
      order.push(data.action);
      return { data: {} };
    });

    const { onChanged } = renderEditor(article(pending), {
      isDirty: true,
      save,
    });
    await userEvent.click(screen.getByTestId("publish-button"));

    await waitFor(() => expect(order).toEqual(["save", "publish_changes"]));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("discards the changes after confirming, without saving", async () => {
    const save = vi.fn(async () => true);
    renderEditor(article(pending), { isDirty: true, save });

    await userEvent.click(
      screen.getByRole("button", { name: "publishing.changes.discard" }),
    );
    // The confirm dialog's button.
    const buttons = await screen.findAllByRole("button", {
      name: "publishing.changes.discard",
    });
    await userEvent.click(buttons[buttons.length - 1]);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/content/blog.article/7/publishing", {
        action: "discard_changes",
      }),
    );
    expect(save).not.toHaveBeenCalled();
  });

  it("compares the changes with the published version", async () => {
    renderEditor(article(pending, { title: "Hello again", intro: "New" }));

    await userEvent.click(
      screen.getByRole("button", { name: "publishing.changes.compare" }),
    );

    const fields = await screen.findByTestId("compare-fields");
    expect(fields).toHaveTextContent("Title");
    expect(fields).toHaveTextContent("again");
    expect(fields).toHaveTextContent("Old intro");
  });
});

describe("PublishingFormat with unpublished changes", () => {
  it("adds a badge to rows with changes", () => {
    render(
      <PublishingFormat
        value={{
          state: "published",
          published_at: null,
          unpublish_at: null,
          has_pending: true,
        }}
      />,
    );

    expect(screen.getByTestId("pending-badge")).toHaveTextContent(
      "publishing.changes.title",
    );
  });
});
