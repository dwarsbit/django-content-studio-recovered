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
import type {
  Model,
  PublishingInfo,
  Resource,
  ReviewDetails,
  ReviewInfo,
} from "@/types";

const get = vi.fn();
const post = vi.fn();

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({ get, post, delete: vi.fn() }),
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

function studio(review: { required: boolean } = { required: false }) {
  return {
    label: "blog.article",
    verbose_name: "article",
    verbose_name_plural: "articles",
    admin: {
      is_singleton: false,
      icon: null,
      edit: { header: [], sidebar: [] },
      list: {
        publishing: {
          unpublish: false,
          can_publish: true,
          pending_changes: true,
          review: { self_approval: false, ...review },
        },
      },
    },
    fields: {
      title: { type: "CharField", verbose_name: "title" },
      intro: { type: "TextField", verbose_name: "intro" },
    },
  } as unknown as Model;
}

const priya = { id: "2", name: "Priya", initials: "P", avatar: null };
const sam = { id: "3", name: "Sam", initials: "S", avatar: null };

function request(values: Partial<ReviewInfo> = {}): ReviewInfo {
  return {
    id: 1,
    status: "open",
    live: false,
    submitted_by: sam,
    submitted_at: new Date().toISOString(),
    reviewer: null,
    note: "Ready for Friday",
    decided_by: null,
    decided_at: null,
    decision_note: "",
    mine: false,
    can_approve: true,
    can_withdraw: true,
    ...values,
  };
}

function article(info: Partial<PublishingInfo>): Resource {
  return {
    id: "7",
    __str__: "Hello",
    title: "Hello",
    __publishing__: {
      state: "draft",
      has_pending: false,
      pending: null,
      published_at: null,
      unpublish_at: null,
      can_publish: true,
      review: null,
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
  {
    model = studio(),
    isDirty = false,
    save = vi.fn(async () => true),
    onChanged = vi.fn(),
  } = {},
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

const details: ReviewDetails = {
  review: request(),
  version: "abc123",
  changes: {
    base: "live",
    fields: ["intro"],
    before: { intro: "Old intro" },
    after: { intro: "New intro" },
  },
  has_pending: true,
  changed_since_submitted: [],
  reviewers: [priya],
};

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockResolvedValue({ data: details });
  post.mockResolvedValue({ data: { review: null } });
});

describe("Review: the editor", () => {
  it("offers Submit for review to someone who cannot publish", () => {
    renderEditor(article({ can_publish: false }));

    expect(screen.getByTestId("publish-button")).toHaveTextContent(
      "review.submit",
    );
    expect(screen.getByTestId("after-review")).toHaveTextContent(
      "review.after_review",
    );
  });

  it("keeps Publish for publishers when review is optional", () => {
    renderEditor(article({}));

    expect(screen.getByTestId("publish-button")).toHaveTextContent(
      "publishing.publish",
    );
  });

  it("sends publishers through review when it is required", () => {
    renderEditor(article({}), { model: studio({ required: true }) });

    expect(screen.getByTestId("publish-button")).toHaveTextContent(
      "review.submit",
    );
  });

  it("submits with a reviewer and a note, saving first", async () => {
    const order: string[] = [];
    const save = vi.fn(async () => {
      order.push("save");
      return true;
    });
    post.mockImplementation(async (url: string, data: { action: string }) => {
      order.push(`${url} ${data.action}`);
      return { data: { review: null } };
    });
    renderEditor(article({ can_publish: false }), { isDirty: true, save });

    await userEvent.click(screen.getByTestId("publish-button"));
    await userEvent.type(
      await screen.findByLabelText("review.submit_dialog.note"),
      "Please check",
    );
    await userEvent.click(screen.getByTestId("review-submit"));

    await waitFor(() =>
      expect(order).toEqual(["save", "/content/blog.article/7/review submit"]),
    );
    expect(post).toHaveBeenCalledWith("/content/blog.article/7/review", {
      action: "submit",
      reviewer: null,
      note: "Please check",
    });
    expect(get).toHaveBeenCalledWith("/content/blog.article/7/review", {
      params: { include: "reviewers" },
    });
  });

  it("shows the request in the card and withdraws it", async () => {
    renderEditor(
      article({
        can_publish: false,
        review: request({ mine: true, can_approve: false }),
      }),
    );

    expect(screen.queryByTestId("publish-button")).toBeNull();
    expect(screen.getAllByTestId("review-badge")[0]).toHaveTextContent(
      "review.states.open",
    );
    const section = screen.getByTestId("review-section");
    expect(section).toHaveTextContent("review.you");
    expect(section).toHaveTextContent("review.anyone");
    // Without comments the card shows the note.
    expect(screen.getByTestId("review-note")).toHaveTextContent(
      "Ready for Friday",
    );

    await userEvent.click(screen.getByTestId("review-withdraw"));
    const buttons = await screen.findAllByRole("button", {
      name: "review.withdraw.ok",
    });
    await userEvent.click(buttons[buttons.length - 1]);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/content/blog.article/7/review", {
        action: "withdraw",
      }),
    );
  });

  it("offers Submit again after changes were requested", () => {
    renderEditor(
      article({
        can_publish: false,
        review: request({
          status: "changes_requested",
          mine: true,
          can_approve: false,
          decided_by: priya,
          decision_note: "Shorter intro, please",
        }),
      }),
    );

    expect(screen.getByTestId("publish-button")).toHaveTextContent(
      "review.submit_again",
    );
    expect(screen.getByTestId("review-note")).toHaveTextContent(
      "Shorter intro, please",
    );
  });
});

describe("Review: the reviewer", () => {
  const live = { state: "published" as const, review: request({ live: true }) };

  it("offers Review and shows the changes", async () => {
    renderEditor(article(live));

    expect(screen.getAllByTestId("review-badge")[0]).toHaveTextContent(
      "review.states.changes_in_review",
    );
    await userEvent.click(screen.getByTestId("review-button"));

    expect(
      await screen.findByTestId("review-submitter-note"),
    ).toHaveTextContent("Ready for Friday");
    const fields = screen.getByTestId("review-fields");
    expect(fields).toHaveTextContent("Intro");
    expect(fields).toHaveTextContent("Old");
    // Live changes go live now: no scheduling.
    expect(
      screen.queryByRole("button", { name: "review.approve_schedule" }),
    ).toBeNull();
  });

  it("approves the version it saw", async () => {
    renderEditor(article(live));

    await userEvent.click(screen.getByTestId("review-button"));
    await screen.findByTestId("review-fields");
    await userEvent.click(screen.getByTestId("review-approve"));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/content/blog.article/7/review", {
        action: "approve",
        version: "abc123",
        note: "",
      }),
    );
  });

  it("needs a note to request changes", async () => {
    renderEditor(article(live));

    await userEvent.click(screen.getByTestId("review-button"));
    await screen.findByTestId("review-fields");
    await userEvent.click(screen.getByTestId("review-request-changes"));
    expect(post).not.toHaveBeenCalled();

    await userEvent.type(
      screen.getByLabelText("review.dialog.note"),
      "Fix the intro",
    );
    await userEvent.click(screen.getByTestId("review-request-changes"));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/content/blog.article/7/review", {
        action: "request_changes",
        note: "Fix the intro",
      }),
    );
  });

  it("warns about edits after submitting", async () => {
    get.mockResolvedValue({
      data: { ...details, changed_since_submitted: ["title"] },
    });
    renderEditor(article(live));

    await userEvent.click(screen.getByTestId("review-button"));

    expect(await screen.findByTestId("review-edited")).toHaveTextContent(
      "review.dialog.edited_since",
    );
  });

  it("hides Review from the submitter without self approval", () => {
    renderEditor(
      article({ review: request({ mine: true, can_approve: false }) }),
    );

    expect(screen.queryByTestId("review-button")).toBeNull();
  });
});

describe("PublishingFormat with review", () => {
  it("shows the review status on rows", () => {
    render(
      <PublishingFormat
        value={{
          state: "draft",
          published_at: null,
          unpublish_at: null,
          review: { status: "changes_requested" },
        }}
      />,
    );

    expect(screen.getByTestId("review-badge")).toHaveTextContent(
      "review.states.changes_requested",
    );
  });
});
