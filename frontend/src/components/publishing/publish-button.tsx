import { useTranslation } from "react-i18next";
import { PiPaperPlaneTiltBold, PiSealCheckBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";

import { usePrimaryAction, usePublishing } from "./publishing";

const LABELS = {
  publish: "publishing.publish",
  publish_now: "publishing.publish_now",
  publish_changes: "publishing.publish_changes",
  submit: "review.submit",
  resubmit: "review.submit_again",
  review: "review.review",
} as const;

/** The header's Publish (now) button, next to Save; with review,
 * Submit for review or Review. */
export function PublishButton({ disabled }: { disabled?: boolean }) {
  const { t } = useTranslation();
  const publishing = usePublishing();
  const primary = usePrimaryAction();

  if (!publishing || !primary) {
    return null;
  }

  const onClick = {
    publish: publishing.publishNow,
    publish_now: publishing.publishNow,
    publish_changes: publishing.publishChanges,
    submit: () => publishing.review?.openSubmit(),
    resubmit: () => publishing.review?.openSubmit(),
    review: () => publishing.review?.openReview(),
  }[primary];

  return (
    <Button
      className="min-w-20"
      isLoading={publishing.isPending}
      disabled={disabled}
      onClick={onClick}
      data-testid={primary === "review" ? "review-button" : "publish-button"}
    >
      {!publishing.isPending &&
        (primary === "review" ? <PiSealCheckBold /> : <PiPaperPlaneTiltBold />)}
      {t(LABELS[primary])}
    </Button>
  );
}
