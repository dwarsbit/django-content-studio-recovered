import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArrowCounterClockwiseBold,
  PiCheckBold,
  PiDotsThreeBold,
} from "react-icons/pi";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { UserAvatar } from "@/components/ui/user-avatar";
import { useComments } from "@/hooks/use-comments";
import useConfirmDialog from "@/hooks/use-confirm-dialog";
import { cn } from "@/lib/utils";
import type { CommentInfo, CommentThread, Id, Model } from "@/types";

import { CommentComposer } from "./comment-composer";
import { MentionText } from "./mention-text";

dayjs.extend(relativeTime);
dayjs.extend(localizedFormat);

// The notes review posts as comments.
const KINDS = {
  "review.submitted": { label: "review.kinds.submitted", tone: "purple" },
  "review.approved": { label: "review.kinds.approved", tone: "green" },
  "review.changes_requested": {
    label: "review.kinds.changes_requested",
    tone: "red",
  },
} as const;

type Change = ReturnType<typeof useComments>["change"];

function Comment({
  model,
  id,
  comment,
  change,
  isPending,
  actions,
}: {
  model: string;
  id: Id;
  comment: CommentInfo;
  change: Change;
  isPending: boolean;
  actions?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const confirm = useConfirmDialog();
  const [editing, setEditing] = useState(false);
  const name = comment.author?.name ?? t("comments.system");

  if (comment.deleted) {
    return (
      <div className="flex items-start gap-2.5" data-testid="comment">
        <div className="size-6 shrink-0 rounded-full border border-dashed" />
        <div className="min-w-0 flex-1">
          <p className="text-sm italic text-muted-foreground">
            {t("comments.deleted")}
          </p>
          {actions}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5" data-testid="comment">
      <UserAvatar
        name={name}
        initials={comment.author?.initials}
        src={comment.author?.avatar}
        className="mt-0.5 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-1.5 min-h-6">
          <span className="text-sm font-medium truncate max-w-full">
            {name}
          </span>
          {comment.kind && comment.kind in KINDS && (
            <Badge
              tone={KINDS[comment.kind as keyof typeof KINDS].tone}
              className="shrink-0"
              data-testid="comment-kind"
            >
              {t(KINDS[comment.kind as keyof typeof KINDS].label)}
            </Badge>
          )}
          <time
            className="text-xs text-muted-foreground shrink-0"
            dateTime={comment.created_at}
            title={dayjs(comment.created_at).format("LLL")}
          >
            {dayjs(comment.created_at).fromNow()}
          </time>
          {comment.edited_at && (
            <span
              className="text-xs text-muted-foreground shrink-0"
              title={dayjs(comment.edited_at).format("LLL")}
            >
              · {t("comments.edited")}
            </span>
          )}
          {(comment.can_edit || comment.can_delete) && !editing && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  size="icon-xs"
                  variant="ghost"
                  className="ml-auto -mr-1 text-muted-foreground"
                  aria-label={t("comments.options")}
                >
                  <PiDotsThreeBold />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {comment.can_edit && (
                  <DropdownMenuItem onSelect={() => setEditing(true)}>
                    {t("common.edit")}
                  </DropdownMenuItem>
                )}
                {comment.can_delete && (
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={async () => {
                      const confirmed = await confirm({
                        title: t("comments.delete_title"),
                        description: t("comments.delete_description"),
                        okText: t("common.delete"),
                      });

                      if (confirmed) {
                        await change({ kind: "delete", comment: comment.id });
                      }
                    }}
                  >
                    {t("common.delete")}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
        {editing ? (
          <div className="mt-1">
            <CommentComposer
              model={model}
              id={id}
              initialBody={comment.body}
              initialMentions={comment.mentions}
              submitLabel={t("common.save")}
              autoFocus
              isPending={isPending}
              onCancel={() => setEditing(false)}
              onSubmit={async (body, mentions) => {
                await change({
                  kind: "edit",
                  comment: comment.id,
                  body,
                  mentions,
                });
                setEditing(false);
              }}
            />
          </div>
        ) : (
          <MentionText body={comment.body} mentions={comment.mentions} />
        )}
        {!editing && actions}
      </div>
    </div>
  );
}

function Thread({
  model,
  id,
  thread,
  change,
  isPending,
}: {
  model: string;
  id: Id;
  thread: CommentThread;
  change: Change;
  isPending: boolean;
}) {
  const { t } = useTranslation();
  const [replying, setReplying] = useState(false);
  const resolved = !!thread.resolved_at;

  return (
    <li
      className={cn("px-5 py-4 space-y-3", resolved && "bg-muted/40")}
      data-testid="comment-thread"
    >
      {resolved && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <PiCheckBold className="size-3" />
          {thread.resolved_by
            ? t("comments.resolved_by", { name: thread.resolved_by.name })
            : t("comments.resolved")}
        </p>
      )}
      <div className={cn(resolved && "opacity-70")}>
        <Comment
          model={model}
          id={id}
          comment={thread}
          change={change}
          isPending={isPending}
          actions={
            <div className="mt-1 flex items-center gap-3 text-xs">
              {!resolved && (
                <button
                  type="button"
                  className="font-medium text-muted-foreground hover:text-foreground"
                  onClick={() => setReplying(true)}
                >
                  {t("comments.reply")}
                </button>
              )}
              {thread.can_resolve && (
                <button
                  type="button"
                  className="flex items-center gap-1 font-medium text-muted-foreground hover:text-foreground"
                  onClick={() =>
                    change({
                      kind: "resolve",
                      comment: thread.id,
                      resolved: !resolved,
                    })
                  }
                >
                  {resolved ? (
                    <>
                      <PiArrowCounterClockwiseBold className="size-3" />
                      {t("comments.reopen")}
                    </>
                  ) : (
                    <>
                      <PiCheckBold className="size-3" />
                      {t("comments.resolve")}
                    </>
                  )}
                </button>
              )}
            </div>
          }
        />
      </div>
      {(thread.replies.length > 0 || replying) && (
        <div
          className={cn(
            "ml-3 space-y-3 border-l pl-4",
            resolved && "opacity-70",
          )}
        >
          {thread.replies.map((reply) => (
            <Comment
              key={reply.id}
              model={model}
              id={id}
              comment={reply}
              change={change}
              isPending={isPending}
            />
          ))}
          {replying && (
            <CommentComposer
              model={model}
              id={id}
              autoFocus
              placeholder={t("comments.reply_placeholder")}
              submitLabel={t("comments.reply")}
              isPending={isPending}
              onCancel={() => setReplying(false)}
              onSubmit={async (body, mentions) => {
                await change({
                  kind: "add",
                  body,
                  mentions,
                  parent: thread.id,
                });
                setReplying(false);
              }}
            />
          )}
        </div>
      )}
    </li>
  );
}

/**
 * The edit page's Comments card: internal notes on the object for the
 * people who work on it, with replies, @mentions and resolving.
 */
export function CommentsCard({ model, id }: { model: Model; id: Id }) {
  const { t } = useTranslation();
  const { data, isLoading, change, isPending } = useComments(model.label, id);
  const [showResolved, setShowResolved] = useState(false);
  const threads = data.threads.filter(
    (thread) => showResolved || !thread.resolved_at,
  );

  const run: Change = async (input) => {
    try {
      return await change(input);
    } catch (error) {
      toast.error(t("comments.error"));
      throw error;
    }
  };

  return (
    <section
      className="rounded-lg border bg-card shadow-xs w-full"
      data-testid="comments-card"
    >
      <div className="px-5 py-3 border-b flex items-center justify-between gap-3">
        <h4 className="font-semibold flex items-center gap-2">
          {t("comments.title")}
          {data.open > 0 && (
            <span className="rounded-full bg-muted px-1.5 text-xs font-medium text-muted-foreground tabular-nums">
              {data.open}
            </span>
          )}
        </h4>
        {data.resolved > 0 && (
          <button
            type="button"
            className="text-xs font-medium text-muted-foreground hover:text-foreground"
            aria-pressed={showResolved}
            onClick={() => setShowResolved((value) => !value)}
            data-testid="comments-resolved-toggle"
          >
            {showResolved
              ? t("comments.hide_resolved")
              : t("comments.show_resolved", { count: data.resolved })}
          </button>
        )}
      </div>
      {!isLoading && threads.length === 0 && (
        <p className="px-5 pt-4 text-sm text-muted-foreground">
          {data.resolved > 0 ? t("comments.all_resolved") : t("comments.empty")}
        </p>
      )}
      {threads.length > 0 && (
        <ul className="divide-y border-b">
          {threads.map((thread) => (
            <Thread
              key={thread.id}
              model={model.label}
              id={id}
              thread={thread}
              change={run}
              isPending={isPending}
            />
          ))}
        </ul>
      )}
      <div className="px-5 py-4">
        <CommentComposer
          model={model.label}
          id={id}
          submitLabel={t("comments.submit")}
          footnote={t("comments.footnote", {
            object: model.verbose_name.toLowerCase(),
          })}
          isPending={isPending}
          onSubmit={(body, mentions) => run({ kind: "add", body, mentions })}
        />
      </div>
    </section>
  );
}
