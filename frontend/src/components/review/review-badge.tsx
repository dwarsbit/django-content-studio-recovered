import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { ReviewStatus } from "@/types";

/**
 * An object's review: In review, or Changes requested; for live
 * content, its changes in review. Nothing once approved or withdrawn.
 */
export function ReviewBadge({
  status,
  live = false,
  className,
}: {
  status: ReviewStatus | null | undefined;
  live?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();

  if (status !== "open" && status !== "changes_requested") {
    return null;
  }

  return (
    <Badge
      tone={status === "open" ? "purple" : "red"}
      className={className}
      data-testid="review-badge"
    >
      {t(
        status === "changes_requested"
          ? "review.states.changes_requested"
          : live
            ? "review.states.changes_in_review"
            : "review.states.open",
      )}
    </Badge>
  );
}
