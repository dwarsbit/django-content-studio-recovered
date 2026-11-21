import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommentsCard } from "@/components/comments/comments-card";
import { mentionQueryAt, splitMentions } from "@/components/comments/mentions";
import type { CommentThread, Model } from "@/types";

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
const confirmMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/hooks/use-confirm-dialog", () => ({
  default: () => confirmMock,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    i18n: { language: "en" },
  }),
}));

const now = new Date().toISOString();
const anna = { id: "1", name: "Anna", initials: "A", avatar: null };
const bob = { id: "2", name: "Bob Smith", initials: "BS", avatar: null };

function thread(overrides: Partial<CommentThread> = {}): CommentThread {
  return {
    id: 1,
    author: anna,
    body: "Can @Bob Smith check the intro?",
    mentions: [bob],
    created_at: now,
    edited_at: null,
    deleted: false,
    can_edit: true,
    can_delete: true,
    resolved_at: null,
    resolved_by: null,
    can_resolve: true,
    replies: [],
    ...overrides,
  };
}

const model = {
  label: "blog.article",
  verbose_name: "Article",
  verbose_name_plural: "Articles",
  admin: { comments: true },
} as unknown as Model;

function renderCard(threads: CommentThread[]) {
  const data = {
    threads,
    open: threads.filter((t) => !t.resolved_at).length,
    resolved: threads.filter((t) => t.resolved_at).length,
  };

  httpMock.get.mockImplementation(async (url: string) =>
    url === "/comments/people" ? { data: { results: [bob] } } : { data },
  );
  httpMock.post.mockResolvedValue({ data });
  httpMock.patch.mockResolvedValue({ data });
  httpMock.delete.mockResolvedValue({ data });

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={client}>
      <CommentsCard model={model} id="7" />
    </QueryClientProvider>,
  );
}

describe("mentions", () => {
  it("splits out the mentioned names, longest first", () => {
    expect(
      splitMentions("Hi @Anna and @Anna de Vries", [
        { ...anna },
        { ...anna, id: "3", name: "Anna de Vries" },
      ]),
    ).toEqual([
      { text: "Hi ", mention: false },
      { text: "@Anna", mention: true },
      { text: " and ", mention: false },
      { text: "@Anna de Vries", mention: true },
    ]);
  });

  it("leaves a text without mentions whole", () => {
    expect(splitMentions("Mail me@example.com", [])).toEqual([
      { text: "Mail me@example.com", mention: false },
    ]);
  });

  it("finds the @query at the caret", () => {
    expect(mentionQueryAt("Hi @bo", 6)).toEqual({ query: "bo", start: 3 });
    expect(mentionQueryAt("@", 1)).toEqual({ query: "", start: 0 });
    expect(mentionQueryAt("me@example", 10)).toBeNull();
    expect(mentionQueryAt("Hi @bob done", 12)).toBeNull();
  });
});

describe("CommentsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows open threads with highlighted mentions", async () => {
    renderCard([
      thread(),
      thread({
        id: 2,
        body: "Old note",
        mentions: [],
        resolved_at: now,
        resolved_by: anna,
      }),
    ]);

    expect(await screen.findAllByTestId("comment-thread")).toHaveLength(1);
    expect(screen.getByTestId("comment-mention")).toHaveTextContent(
      "@Bob Smith",
    );
    expect(httpMock.get).toHaveBeenCalledWith("/comments", {
      params: { model: "blog.article", id: "7" },
    });

    await userEvent.click(screen.getByTestId("comments-resolved-toggle"));

    expect(screen.getAllByTestId("comment-thread")).toHaveLength(2);
    expect(screen.getByText("Old note")).toBeInTheDocument();
  });

  it("posts a comment with the people picked from the @ list", async () => {
    renderCard([]);

    const input = await screen.findByTestId("comment-input");

    await userEvent.type(input, "Thanks @bo");
    const list = await screen.findByTestId("mention-list");
    await userEvent.click(within(list).getByText("Bob Smith"));
    await userEvent.type(input, "looks good");
    await userEvent.click(screen.getByTestId("comment-submit"));

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith("/comments", {
        model: "blog.article",
        id: "7",
        body: "Thanks @Bob Smith looks good",
        mentions: ["2"],
        parent: null,
      }),
    );
    expect(input).toHaveValue("");
  });

  it("drops a mention whose name was removed from the text", async () => {
    renderCard([]);

    const input = await screen.findByTestId("comment-input");

    await userEvent.type(input, "@b");
    await userEvent.keyboard("{Enter}");
    expect(input).toHaveValue("@Bob Smith ");

    await userEvent.clear(input);
    await userEvent.type(input, "Never mind{Control>}{Enter}{/Control}");

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith(
        "/comments",
        expect.objectContaining({ body: "Never mind", mentions: [] }),
      ),
    );
  });

  it("replies in a thread and resolves it", async () => {
    renderCard([thread()]);

    await userEvent.click(await screen.findByText("comments.reply"));
    const inputs = screen.getAllByTestId("comment-input");
    await userEvent.type(inputs[0], "On it");
    await userEvent.click(screen.getAllByTestId("comment-submit")[0]);

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith("/comments", {
        model: "blog.article",
        id: "7",
        body: "On it",
        mentions: [],
        parent: 1,
      }),
    );

    await userEvent.click(screen.getByText("comments.resolve"));

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith("/comments/1/resolve", {
        resolved: true,
      }),
    );
  });

  it("shows a deleted comment with replies as a placeholder", async () => {
    renderCard([
      thread({
        deleted: true,
        body: "",
        mentions: [],
        can_edit: false,
        can_delete: false,
        replies: [
          {
            ...thread({ id: 3, body: "A reply", mentions: [] }),
          },
        ],
      }),
    ]);

    expect(await screen.findByText("comments.deleted")).toBeInTheDocument();
    expect(screen.getByText("A reply")).toBeInTheDocument();
  });
});
