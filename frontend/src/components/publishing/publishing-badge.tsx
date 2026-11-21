import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import { useTranslation } from "react-i18next";
import { PiClockBold } from "react-icons/pi";

import { Badge } from "@/components/ui/badge";
import type { PublishingInfo, PublishingState } from "@/types";

dayjs.extend(localizedFormat);

const TONES = {
  draft: "gray",
  scheduled: "blue",
  published: "green",
  expired: "yellow",
} as const;

/**
 * An object's publishing state: Draft, Scheduled, Published or Expired.
 * Scheduled shows when the object goes live, unless `short`.
 */
export function PublishingBadge({
  state,
  publishedAt,
  short = false,
  className,
}: {
  state: PublishingState;
  publishedAt?: string | null;
  short?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();

  return (
    <Badge
      tone={TONES[state] ?? "gray"}
      className={className}
      data-testid="publishing-badge"
    >
      {state === "scheduled" && <PiClockBold />}
      {state === "scheduled" && !short && publishedAt
        ? t("publishing.scheduled_for", {
            time: dayjs(publishedAt).format("D MMM, LT"),
          })
        : t(`publishing.states.${state}`)}
    </Badge>
  );
}

/** The Status column of studios with publishing: a row's state. */
export function PublishingFormat({ value }: { value: unknown }) {
  const info = value as PublishingInfo | null | undefined;

  if (!info?.state) {
    return null;
  }

  return <PublishingBadge state={info.state} publishedAt={info.published_at} />;
}
