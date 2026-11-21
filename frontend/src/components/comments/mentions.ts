import type { CommentPerson } from "@/types";

function escape(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Splits a comment's text into plain parts and the "@Name" parts of
 * the people it mentions. */
export function splitMentions(body: string, mentions: CommentPerson[]) {
  const names = mentions
    .map((person) => person.name)
    .filter(Boolean)
    // Longest first, so "@Anna de Vries" wins over "@Anna".
    .sort((a, b) => b.length - a.length);

  if (!names.length) {
    return [{ text: body, mention: false }];
  }

  const tags = new Set(names.map((name) => `@${name}`));
  const pattern = new RegExp(`(@(?:${names.map(escape).join("|")}))`);

  return body
    .split(pattern)
    .filter((text) => text !== "")
    .map((text) => ({ text, mention: tags.has(text) }));
}

/** The "@query" the caret is in, if any: "@" at the start or after a
 * space, followed by up to 30 characters without spaces. */
export function mentionQueryAt(text: string, caret: number) {
  const match = /(^|\s)@([^\s@]{0,30})$/.exec(text.slice(0, caret));

  if (!match) {
    return null;
  }

  return { query: match[2], start: caret - match[2].length - 1 };
}
