import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import { createContext, useContext } from "react";

import type { PublishingInfo } from "@/types";

dayjs.extend(localizedFormat);

export type PublishingAction =
  "publish" | "schedule" | "unpublish" | "set_unpublish_at";

export interface PublishingControls {
  info: PublishingInfo;
  // Whether objects can get an unpublish date.
  unpublish: boolean;
  // Whether the user may publish this object.
  canPublish: boolean;
  isPending: boolean;
  publishNow(): Promise<void>;
  openSchedule(): void;
  cancelSchedule(): Promise<void>;
  unpublishNow(): Promise<void>;
  openUnpublishDate(): void;
}

export const PublishingContext = createContext<PublishingControls | null>(null);

/** The edit page's publishing, for its header and Publishing card. */
export function usePublishing() {
  return useContext(PublishingContext);
}

/**
 * Whether the edit page's header offers Publish: content that is not
 * live, for a user who may publish it.
 */
export function useShowPublishButton() {
  const publishing = usePublishing();

  return (
    !!publishing &&
    publishing.canPublish &&
    publishing.info.state !== "published"
  );
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
