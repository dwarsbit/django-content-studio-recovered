import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import { createContext, useContext } from "react";

import type { PublishingInfo, ReviewInfo } from "@/types";

dayjs.extend(localizedFormat);

export type PublishingAction =
  | "publish"
  | "schedule"
  | "unpublish"
  | "set_unpublish_at"
  | "publish_changes"
  | "discard_changes";

export type ReviewAction =
  "submit" | "withdraw" | "approve" | "request_changes";

export interface PublishingControls {
  info: PublishingInfo;
  // Whether objects can get an unpublish date.
  unpublish: boolean;
  // Whether the user may publish this object.
  canPublish: boolean;
  isPending: boolean;
  // Whether the live object has changes to publish: unpublished
  // changes, or unsaved ones that saving keeps unpublished.
  hasChanges: boolean;
  // Whether the user may discard the unpublished changes.
  canDiscard: boolean;
  publishNow(): Promise<void>;
  publishChanges(): Promise<void>;
  discardChanges(): Promise<void>;
  openCompare(): void;
  // A field's name as the form shows it.
  fieldLabel(name: string): string;
  openSchedule(): void;
  cancelSchedule(): Promise<void>;
  unpublishNow(): Promise<void>;
  openUnpublishDate(): void;
  // Review before publishing (the review app), or null without it.
  review: ReviewControls | null;
}

export interface ReviewControls {
  // Whether publishers go through review too.
  required: boolean;
  // The object's current request, or null.
  current: ReviewInfo | null;
  // Whether the user may submit it (change permission).
  canSubmit: boolean;
  // Whether the studio has comments, which hold the review notes.
  comments: boolean;
  openSubmit(): void;
  openReview(): void;
  withdraw(): Promise<void>;
}

// The header's main publishing button.
export type PrimaryAction =
  | "publish"
  | "publish_now"
  | "publish_changes"
  | "submit"
  | "resubmit"
  | "review";

export const PublishingContext = createContext<PublishingControls | null>(null);

/** The edit page's publishing, for its header and Publishing card. */
export function usePublishing() {
  return useContext(PublishingContext);
}

/**
 * Whether the edit page's header offers Publish: content that is not
 * live, or live content with changes to publish, for a user who may
 * publish it.
 */
export function useShowPublishButton() {
  return usePrimaryAction() !== null;
}

/**
 * The header's main publishing button, if any: Publish (now, or the
 * changes) for someone who may publish; with review, Submit for review
 * (again, after changes were requested) for editors, and Review for
 * someone who may approve the request in review.
 */
export function usePrimaryAction(): PrimaryAction | null {
  const publishing = usePublishing();

  if (!publishing) {
    return null;
  }

  const { info, canPublish, hasChanges, review } = publishing;
  const live = info.state === "published";

  if (review) {
    const { current } = review;

    if (current?.status === "open") {
      return current.can_approve ? "review" : null;
    }

    if (current?.status === "changes_requested") {
      return review.canSubmit ? "resubmit" : null;
    }

    if (!canPublish || review.required) {
      const submittable =
        info.state === "draft" || info.state === "expired" || hasChanges;

      return review.canSubmit && submittable ? "submit" : null;
    }
  }

  if (!canPublish || (live && !hasChanges)) {
    return null;
  }

  return live
    ? "publish_changes"
    : info.state === "scheduled"
      ? "publish_now"
      : "publish";
}

/** The browser's time zone, which the pickers show times in. */
export function timeZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

export function formatTime(value: string) {
  return dayjs(value).format("llll");
}

/** A date short enough for the Publishing card: the year only when
 * it is not this year's. */
export function formatShortTime(value: string) {
  const date = dayjs(value);

  return date.format(
    date.year() === dayjs().year() ? "ddd D MMM, LT" : "D MMM YYYY, LT",
  );
}
