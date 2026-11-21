import { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { UserAvatar } from "@/components/ui/user-avatar";
import { useMentionable } from "@/hooks/use-comments";
import { cn } from "@/lib/utils";
import type { CommentPerson, Id } from "@/types";

import { mentionQueryAt } from "./mentions";

/**
 * A textarea for a comment, with an @ list of the people who can be
 * mentioned. Ctrl/Cmd+Enter posts it.
 */
export function CommentComposer({
  model,
  id,
  initialBody = "",
  initialMentions = [],
  placeholder,
  footnote,
  submitLabel,
  autoFocus,
  isPending,
  onSubmit,
  onCancel,
}: {
  model: string;
  id: Id;
  initialBody?: string;
  initialMentions?: CommentPerson[];
  placeholder?: string;
  footnote?: React.ReactNode;
  submitLabel: string;
  autoFocus?: boolean;
  isPending?: boolean;
  onSubmit(body: string, mentions: Id[]): Promise<unknown>;
  onCancel?(): void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [body, setBody] = useState(initialBody);
  const [mentioned, setMentioned] = useState<CommentPerson[]>(initialMentions);
  const [mention, setMention] = useState<{
    query: string;
    start: number;
  } | null>(null);
  const [active, setActive] = useState(0);
  // Where the caret goes after a mention is picked.
  const caret = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (caret.current !== null && ref.current) {
      ref.current.focus();
      ref.current.setSelectionRange(caret.current, caret.current);
      caret.current = null;
    }
  }, [body]);
  const { data: people = [] } = useMentionable(
    model,
    id,
    mention ? mention.query : null,
  );
  const open = !!mention && people.length > 0;

  const track = (text: string, position: number) => {
    const next = mentionQueryAt(text, position);

    setMention(next);

    if (next?.query !== mention?.query) {
      setActive(0);
    }
  };

  const pick = (person: CommentPerson) => {
    if (!mention) {
      return;
    }

    const end = mention.start + mention.query.length + 1;
    const tag = `@${person.name} `;
    const text = body.slice(0, mention.start) + tag + body.slice(end);

    setBody(text);
    setMention(null);
    setMentioned((current) =>
      current.some((p) => p.id === person.id) ? current : [...current, person],
    );
    caret.current = mention.start + tag.length;
  };

  const submit = async () => {
    const text = body.trim();

    if (!text || isPending) {
      return;
    }

    // Only the people still named in the text.
    const mentions = mentioned
      .filter((person) => text.includes(`@${person.name}`))
      .map((person) => person.id);

    await onSubmit(text, mentions);
    setBody("");
    setMentioned([]);
    setMention(null);
  };

  return (
    <div className="space-y-2">
      <div className="relative">
        <Textarea
          ref={ref}
          value={body}
          autoFocus={autoFocus}
          placeholder={placeholder ?? t("comments.placeholder")}
          aria-label={placeholder ?? t("comments.placeholder")}
          className="min-h-16 text-sm resize-none"
          data-testid="comment-input"
          onChange={(event) => {
            setBody(event.target.value);
            track(event.target.value, event.target.selectionStart);
          }}
          onSelect={(event) =>
            track(event.currentTarget.value, event.currentTarget.selectionStart)
          }
          onBlur={() => setTimeout(() => setMention(null), 150)}
          onKeyDown={(event) => {
            if (open) {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((idx) => (idx + 1) % people.length);
                return;
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((idx) => (idx - 1 + people.length) % people.length);
                return;
              }
              if (event.key === "Enter" || event.key === "Tab") {
                event.preventDefault();
                pick(people[Math.min(active, people.length - 1)]);
                return;
              }
            }
            if (event.key === "Escape") {
              if (mention) {
                event.preventDefault();
                event.stopPropagation();
                setMention(null);
              } else if (onCancel) {
                event.preventDefault();
                onCancel();
              }
              return;
            }
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {open && (
          <ul
            role="listbox"
            aria-label={t("comments.mention")}
            className="absolute left-0 right-0 top-full z-50 mt-1 max-h-56 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
            data-testid="mention-list"
          >
            {people.map((person, idx) => (
              <li
                key={person.id}
                role="option"
                aria-selected={idx === active}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm",
                  idx === active && "bg-accent text-accent-foreground",
                )}
                onMouseEnter={() => setActive(idx)}
                onMouseDown={(event) => {
                  // Keep the textarea's focus.
                  event.preventDefault();
                  pick(person);
                }}
              >
                <UserAvatar
                  name={person.name}
                  initials={person.initials}
                  src={person.avatar}
                  className="size-5"
                />
                <span className="truncate">{person.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex items-center justify-end gap-2">
        {footnote && (
          <p className="mr-auto text-xs text-muted-foreground">{footnote}</p>
        )}
        {onCancel && (
          <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="shrink-0"
          disabled={!body.trim() || isPending}
          onClick={submit}
          data-testid="comment-submit"
        >
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
