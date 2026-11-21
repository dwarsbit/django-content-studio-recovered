import type { CommentPerson } from "@/types";

import { splitMentions } from "./mentions";

/** A comment's text with its mentions highlighted. */
export function MentionText({
  body,
  mentions,
}: {
  body: string;
  mentions: CommentPerson[];
}) {
  return (
    <p className="text-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
      {splitMentions(body, mentions).map((part, idx) =>
        part.mention ? (
          <span
            key={idx}
            className="font-medium text-violet-600 dark:text-violet-400"
            data-testid="comment-mention"
          >
            {part.text}
          </span>
        ) : (
          <span key={idx}>{part.text}</span>
        ),
      )}
    </p>
  );
}
