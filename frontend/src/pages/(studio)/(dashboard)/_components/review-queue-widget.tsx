import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ReviewBadge } from "@/components/review/review-badge";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { UserAvatar } from "@/components/ui/user-avatar";
import { useHttp } from "@/hooks/use-http";
import { cn } from "@/lib/utils";
import type {
  CommentPerson,
  DashboardWidget,
  DateTimeString,
  ReviewStatus,
} from "@/types";

import { widgetRefetchInterval } from "./refresh";
import { Widget, WidgetEmpty, WidgetLoading } from "./widget";

dayjs.extend(relativeTime);

export interface ReviewQueueData {
  title: string;
  description: string;
  // "review": waiting for the user's review; "mine": the user's own.
  mode: "review" | "mine";
  total: number;
  results: {
    id: number;
    model: string;
    model_name: string;
    object_id: string;
    title: string;
    status: ReviewStatus;
    live: boolean;
    submitted_by: CommentPerson | null;
    submitted_at: DateTimeString;
    reviewer: CommentPerson | null;
  }[];
}

/**
 * Review requests: for someone who can publish, the ones waiting for
 * their review, oldest first; for an editor, their own in review or
 * with changes requested.
 */
export function ReviewQueueWidget({ widget }: { widget: DashboardWidget }) {
  const http = useHttp();
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["dashboard", "widget", widget.widget_id],
    refetchInterval: widgetRefetchInterval(widget),
    async queryFn() {
      const { data } = await http.get<ReviewQueueData>(
        `/dashboard/widgets/${widget.widget_id}`,
      );

      return data;
    },
  });

  return (
    <Widget
      title={
        <span className="flex items-center gap-2">
          <span className="truncate">{data?.title ?? widget.name}</span>
          {data?.total ? (
            <span className="rounded-full bg-primary text-primary-foreground px-1.5 text-[11px] font-semibold leading-[18px] tabular-nums">
              {data.total}
            </span>
          ) : null}
        </span>
      }
      description={data?.description || undefined}
    >
      {!data ? (
        <WidgetLoading />
      ) : data.results.length === 0 ? (
        <WidgetEmpty>
          {t(
            data.mode === "review"
              ? "review.widget.empty"
              : "review.widget.empty_mine",
          )}
        </WidgetEmpty>
      ) : (
        <ul className="border-t p-1.5" data-testid="review-queue">
          {data.results.map((item) => (
            <li key={item.id}>
              <Link
                to={`/content/${item.model}/${item.object_id}`}
                className="flex items-center gap-3 rounded-md px-2.5 py-2 hover:bg-accent outline-none focus-visible:ring-3 focus-visible:ring-ring"
              >
                {item.submitted_by && (
                  <UserAvatar
                    name={item.submitted_by.name}
                    initials={item.submitted_by.initials}
                    src={item.submitted_by.avatar}
                    className="size-8 shrink-0"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{item.title}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {item.submitted_by && data.mode === "review"
                      ? t("review.widget.submitted_by", {
                          name: item.submitted_by.name,
                          when: dayjs(item.submitted_at).fromNow(),
                        })
                      : t("review.widget.submitted", {
                          when: dayjs(item.submitted_at).fromNow(),
                        })}
                  </div>
                </div>
                {data.mode === "review" ? (
                  <>
                    <Badge tone={item.live ? "yellow" : "blue"}>
                      {item.live
                        ? t("review.widget.changes")
                        : t("review.widget.new", { model: item.model_name })}
                    </Badge>
                    <span
                      className={cn(
                        buttonVariants({ variant: "outline", size: "sm" }),
                        "shrink-0 max-sm:hidden",
                      )}
                    >
                      {t("review.review")}
                    </span>
                  </>
                ) : (
                  <ReviewBadge status={item.status} live={item.live} />
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
