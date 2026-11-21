import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useTranslation } from "react-i18next";
import {
  PiArrowsLeftRightBold,
  PiCalendarBlankBold,
  PiGlobeBold,
  PiInfoBold,
  PiSealCheckBold,
} from "react-icons/pi";

import { ReviewBadge } from "@/components/review/review-badge";
import { Button } from "@/components/ui/button";
import { UserAvatar } from "@/components/ui/user-avatar";
import type { ReviewInfo } from "@/types";

import { formatShortTime, timeZone, usePublishing } from "./publishing";
import { PublishingBadge } from "./publishing-badge";

dayjs.extend(relativeTime);

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
  const { t, i18n } = useTranslation();
  const publishing = usePublishing();

  if (!publishing) {
    return null;
  }

  const { info, canPublish, isPending } = publishing;
  const { state } = info;
  const live = state === "published" || state === "expired";
  const review = publishing.review;
  const current =
    review?.current?.status === "open" ||
    review?.current?.status === "changes_requested"
      ? review.current
      : null;
  // Whether it goes live through review: for editors, and for everyone
  // on studios that require it.
  const throughReview = !!review && (!canPublish || review.required);

  return (
    <section
      className="rounded-lg border bg-card shadow-xs w-full"
      data-testid="publishing-card"
    >
      <div className="px-5 py-3 border-b flex items-center justify-between gap-3">
        <h4 className="font-semibold">{t("publishing.title")}</h4>
        <div className="flex flex-wrap items-center justify-end gap-1.5 min-w-0">
          <PublishingBadge state={state} short />
          <ReviewBadge status={current?.status} live={current?.live} />
        </div>
      </div>
      <div className="p-5 pt-3 space-y-1">
        <Row label={t(live ? "publishing.published" : "publishing.publish_on")}>
          {state === "draft" || !info.published_at ? (
            throughReview || current?.status === "open" ? (
              <span
                className="text-muted-foreground font-normal"
                data-testid="after-review"
              >
                {t("review.after_review")}
              </span>
            ) : canPublish ? (
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
        {info.pending && (
          <div
            className="pt-3 mt-2 border-t space-y-2"
            data-testid="pending-changes"
          >
            <div className="text-sm font-semibold pt-1">
              {t("publishing.changes.title")}
            </div>
            <div className="text-sm">
              <span className="font-medium">
                {new Intl.ListFormat(i18n.language, {
                  type: "conjunction",
                }).format(info.pending.fields.map(publishing.fieldLabel))}
              </span>
              <span className="text-muted-foreground">
                {" · "}
                {info.pending.edited_by
                  ? t("publishing.changes.saved_by", {
                      name: info.pending.edited_by,
                      when: dayjs(info.pending.edited_at).fromNow(),
                    })
                  : t("publishing.changes.saved", {
                      when: dayjs(info.pending.edited_at).fromNow(),
                    })}
              </span>
            </div>
            <p className="text-xs text-muted-foreground flex gap-1.5">
              <PiInfoBold className="shrink-0 mt-0.5" />
              {t("publishing.changes.hint")}
            </p>
            <div className="flex gap-2 pt-1">
              <Button
                variant="outline"
                size="sm"
                className="flex-1"
                onClick={publishing.openCompare}
              >
                <PiArrowsLeftRightBold />
                {t("publishing.changes.compare")}
              </Button>
              {publishing.canDiscard && (
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 text-destructive"
                  disabled={isPending}
                  onClick={publishing.discardChanges}
                >
                  {t("publishing.changes.discard")}
                </Button>
              )}
            </div>
          </div>
        )}
        {current && <ReviewSection review={current} />}
        {!current && throughReview && !canPublish && (
          <p className="text-xs text-muted-foreground pt-2 flex gap-1.5">
            <PiInfoBold className="shrink-0 mt-0.5" />
            {t("review.hint")}
          </p>
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

/** The object's request in review, or the changes asked for. */
function ReviewSection({ review }: { review: ReviewInfo }) {
  const { t } = useTranslation();
  const publishing = usePublishing()!;
  const controls = publishing.review!;
  const submitter = review.submitted_by;
  const changes = review.status === "changes_requested";
  // Comments hold the notes when the studio has them.
  const note = changes
    ? review.decision_note
    : controls.comments
      ? ""
      : review.note;

  return (
    <div className="pt-3 mt-2 border-t space-y-1" data-testid="review-section">
      <div className="text-sm font-semibold pt-1 pb-1">
        {t(changes ? "review.states.changes_requested" : "review.title")}
      </div>
      <Row label={t("review.submitted")}>
        {submitter && (
          <UserAvatar
            name={submitter.name}
            initials={submitter.initials}
            src={submitter.avatar}
            className="size-5"
          />
        )}
        <span className="truncate">
          {review.mine ? t("review.you") : (submitter?.name ?? "")}
        </span>
        <span className="text-muted-foreground font-normal shrink-0">
          {dayjs(review.submitted_at).fromNow()}
        </span>
      </Row>
      {changes && review.decided_by ? (
        <Row label={t("review.reviewed_by")}>
          <span className="truncate">{review.decided_by.name}</span>
        </Row>
      ) : (
        <Row label={t("review.reviewer")}>
          {review.reviewer ? (
            <span className="truncate">{review.reviewer.name}</span>
          ) : (
            <span className="text-muted-foreground font-normal truncate">
              {t("review.anyone")}
            </span>
          )}
        </Row>
      )}
      {note && (
        <p
          className="rounded-md bg-muted px-3 py-2 text-sm whitespace-pre-wrap break-words"
          data-testid="review-note"
        >
          {note}
        </p>
      )}
      {(review.can_approve || review.can_withdraw) && (
        <div className="flex gap-2 pt-2">
          {review.can_approve && (
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              disabled={publishing.isPending}
              onClick={controls.openReview}
            >
              <PiSealCheckBold />
              {t("review.review")}
            </Button>
          )}
          {review.can_withdraw && !changes && (
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              disabled={publishing.isPending}
              onClick={controls.withdraw}
              data-testid="review-withdraw"
            >
              {t("review.withdraw.ok")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
