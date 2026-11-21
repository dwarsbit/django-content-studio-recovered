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
  useTranslation: () => ({ t: (key: string) => key }),
}));

const model = {
  label: "blog.article",
  verbose_name: "article",
  verbose_name_plural: "articles",
  admin: {
    is_singleton: false,
    icon: null,
    edit: { header: [], sidebar: [] },
    list: { publishing: { unpublish: true, can_publish: true } },
  },
  fields: {},
} as unknown as Model;

function article(info: Partial<PublishingInfo>): Resource {
  return {
    id: "7",
    __str__: "Hello",
    __publishing__: {
      state: "draft",
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

describe("Publishing", () => {
  it("publishes a draft from the header", async () => {
    const { onChanged } = renderEditor(article({}));

    expect(screen.getByTestId("publishing-card")).toHaveTextContent(
      "publishing.states.draft",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "publishing.publish" }),
    );

    expect(post).toHaveBeenCalledWith("/content/blog.article/7/publishing", {
      action: "publish",
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("saves unsaved changes before publishing", async () => {
    const order: string[] = [];
    const save = vi.fn(async () => {
      order.push("save");
      return true;
    });
    post.mockImplementation(async () => {
      order.push("publish");
      return { data: {} };
    });

    renderEditor(article({}), { isDirty: true, save });
    await userEvent.click(
      screen.getByRole("button", { name: "publishing.publish" }),
    );

    await waitFor(() => expect(order).toEqual(["save", "publish"]));
  });

  it("does not publish when the save fails", async () => {
    renderEditor(article({}), {
      isDirty: true,
      save: vi.fn(async () => false),
    });

    await userEvent.click(
      screen.getByRole("button", { name: "publishing.publish" }),
    );

    expect(post).not.toHaveBeenCalled();
  });

  it("offers publish now and cancel schedule for scheduled content", async () => {
    renderEditor(
      article({ state: "scheduled", published_at: "2030-01-01T09:00:00Z" }),
    );

    expect(
      screen.getByRole("button", { name: "publishing.publish_now" }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "publishing.cancel_schedule.ok" }),
    );
    // The confirmation dialog's OK button.
    const buttons = await screen.findAllByRole("button", {
      name: "publishing.cancel_schedule.ok",
    });
    await userEvent.click(buttons[buttons.length - 1]);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/content/blog.article/7/publishing", {
        action: "unpublish",
      }),
    );
  });

  it("keeps a plain Save for published content", () => {
    renderEditor(
      article({ state: "published", published_at: "2020-01-01T09:00:00Z" }),
    );

    expect(
      screen.queryByRole("button", { name: "publishing.publish" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "publishing.unpublish.ok" }),
    ).toBeInTheDocument();
  });

  it("schedules from the card", async () => {
    renderEditor(article({}));

    await userEvent.click(
      screen.getByRole("button", { name: /publishing.schedule.open/ }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "publishing.schedule.submit" }),
    );

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/content/blog.article/7/publishing",
        expect.objectContaining({ action: "schedule", unpublish_at: null }),
      ),
    );
    expect(post.mock.calls[0][1].at).toMatch(/^\d{4}-\d\d-\d\dT09:00:00/);
  });

  it("shows only the state to users who may not publish", () => {
    renderEditor(article({ can_publish: false }));

    expect(
      screen.queryByRole("button", { name: "publishing.publish" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /publishing.schedule.open/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("publishing-card")).toHaveTextContent(
      "publishing.not_scheduled",
    );
  });
});

describe("PublishingFormat", () => {
  it("shows a row's state", () => {
    render(
      <PublishingFormat
        value={{ state: "expired", published_at: null, unpublish_at: null }}
      />,
    );

    expect(screen.getByTestId("publishing-badge")).toHaveTextContent(
      "publishing.states.expired",
    );
  });

  it("shows nothing without a state", () => {
    const { container } = render(<PublishingFormat value={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("Nested editors", () => {
  it("hide the publishing of the editor around them", () => {
    const category = {
      ...model,
      label: "blog.category",
      admin: { ...model.admin, list: { publishing: null } },
    } as unknown as Model;

    render(
      <QueryClientProvider client={new QueryClient()}>
        <PublishingProvider
          model={model}
          resource={article({})}
          resourcePath="/content/blog.article"
          isDirty={false}
          readOnly={false}
          save={vi.fn()}
          onChanged={vi.fn()}
        >
          <PublishingProvider
            model={category}
            resource={{ id: "1", __str__: "Design" } as Resource}
            resourcePath="/content/blog.category"
            isDirty={false}
            readOnly={false}
            save={vi.fn()}
            onChanged={vi.fn()}
          >
            <PublishingCard />
          </PublishingProvider>
        </PublishingProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByTestId("publishing-card")).not.toBeInTheDocument();
  });
});
