import { useTranslation } from "react-i18next";
import { PiCalendarBlankBold, PiGlobeBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";

import { formatShortTime, timeZone, usePublishing } from "./publishing";
import { PublishingBadge } from "./publishing-badge";

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 min-h-8">
      <span className="text-sm text-muted-foreground shrink-0">{label}</span>
      <div className="flex items-center gap-1.5 text-sm font-medium min-w-0">
        {children}
      </div>
    </div>
  );
}

/**
 * The top of the edit page's sidebar on studios with publishing: the
 * object's state, when it goes live and comes down, and the changes
 * the user may make.
 */
export function PublishingCard() {
  const { t } = useTranslation();
  const publishing = usePublishing();

  if (!publishing) {
    return null;
  }

  const { info, canPublish, isPending } = publishing;
  const { state } = info;
  const live = state === "published" || state === "expired";

  return (
    <section
      className="rounded-lg border bg-card shadow-xs w-full"
      data-testid="publishing-card"
    >
      <div className="px-5 py-3 border-b flex items-center justify-between gap-3">
        <h4 className="font-semibold">{t("publishing.title")}</h4>
        <PublishingBadge state={state} short />
      </div>
      <div className="p-5 pt-3 space-y-1">
        <Row label={t(live ? "publishing.published" : "publishing.publish_on")}>
          {state === "draft" || !info.published_at ? (
            canPublish ? (
              <Button
                variant="outline"
                size="sm"
                disabled={isPending}
                onClick={publishing.openSchedule}
              >
                <PiCalendarBlankBold />
                {t("publishing.schedule.open")}
              </Button>
            ) : (
              <span className="text-muted-foreground font-normal">
                {t("publishing.not_scheduled")}
              </span>
            )
          ) : (
            <>
              <span className="truncate">
                {formatShortTime(info.published_at)}
              </span>
              {state === "scheduled" && canPublish && (
                <Button
                  variant="ghost"
                  size="xs"
                  disabled={isPending}
                  onClick={publishing.openSchedule}
                >
                  {t("common.edit")}
                </Button>
              )}
            </>
          )}
        </Row>
        {publishing.unpublish && (
          <Row label={t("publishing.unpublish_on")}>
            {info.unpublish_at ? (
              <span className="truncate">
                {formatShortTime(info.unpublish_at)}
              </span>
            ) : (
              <span className="text-muted-foreground font-normal">
                {t("publishing.never")}
              </span>
            )}
            {state !== "draft" && state !== "expired" && canPublish && (
              <Button
                variant="ghost"
                size="xs"
                disabled={isPending}
                onClick={
                  state === "scheduled"
                    ? publishing.openSchedule
                    : publishing.openUnpublishDate
                }
              >
                {t(info.unpublish_at ? "common.edit" : "publishing.set")}
              </Button>
            )}
          </Row>
        )}
        {canPublish && state === "published" && (
          <div className="pt-3">
            <Button
              variant="outline"
              size="sm"
              className="w-full text-destructive"
              disabled={isPending}
              onClick={publishing.unpublishNow}
            >
              {t("publishing.unpublish.ok")}
            </Button>
          </div>
        )}
        {canPublish && state === "scheduled" && (
          <div className="pt-3">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={isPending}
              onClick={publishing.cancelSchedule}
            >
              {t("publishing.cancel_schedule.ok")}
            </Button>
          </div>
        )}
        {state === "scheduled" && (
          <p className="text-xs text-muted-foreground pt-2 flex items-center gap-1">
            <PiGlobeBold className="shrink-0" />
            {t("publishing.time_zone", { zone: timeZone() })}
          </p>
        )}
      </div>
    </section>
  );
}
