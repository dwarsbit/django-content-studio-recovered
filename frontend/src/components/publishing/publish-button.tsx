import { useTranslation } from "react-i18next";
import { PiPaperPlaneTiltBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";

import { usePublishing, useShowPublishButton } from "./publishing";

/** The header's Publish (now) button, next to Save. */
export function PublishButton({ disabled }: { disabled?: boolean }) {
  const { t } = useTranslation();
  const publishing = usePublishing();
  const show = useShowPublishButton();

  if (!publishing || !show) {
    return null;
  }

  const live = publishing.info.state === "published";

  return (
    <Button
      className="min-w-20"
      isLoading={publishing.isPending}
      disabled={disabled}
      onClick={live ? publishing.publishChanges : publishing.publishNow}
      data-testid="publish-button"
    >
      {!publishing.isPending && <PiPaperPlaneTiltBold />}
      {t(
        live
          ? "publishing.publish_changes"
          : publishing.info.state === "scheduled"
            ? "publishing.publish_now"
            : "publishing.publish",
      )}
    </Button>
  );
}
