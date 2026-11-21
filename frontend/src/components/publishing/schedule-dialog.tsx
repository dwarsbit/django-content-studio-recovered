import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiClockBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { DateTimeWidget } from "@/components/widgets/date-time-widget";
import { FieldType, type ModelField, type PublishingInfo } from "@/types";

import { formatTime, timeZone } from "./publishing";

dayjs.extend(localizedFormat);

const REQUIRED: ModelField = { type: FieldType.DateTimeField, required: true };

// The days before today are not offered.
function today() {
  return { min_date: dayjs().format("YYYY-MM-DD") };
}

/**
 * Schedule an object: when it goes live and, on studios with an
 * unpublish date, when it comes down again.
 */
export function ScheduleDialog({
  open,
  onOpenChange,
  name,
  info,
  unpublish,
  isPending,
  onSchedule,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  name: string;
  info: PublishingInfo;
  unpublish: boolean;
  isPending: boolean;
  onSchedule(at: string, unpublishAt: string | null): Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {/* Mounted per opening, so it starts from the object's dates. */}
        {open && (
          <ScheduleForm
            name={name}
            info={info}
            unpublish={unpublish}
            isPending={isPending}
            onCancel={() => onOpenChange(false)}
            onSchedule={onSchedule}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ScheduleForm({
  name,
  info,
  unpublish,
  isPending,
  onCancel,
  onSchedule,
}: {
  name: string;
  info: PublishingInfo;
  unpublish: boolean;
  isPending: boolean;
  onCancel(): void;
  onSchedule(at: string, unpublishAt: string | null): Promise<void>;
}) {
  const { t } = useTranslation();
  const scheduled = info.state === "scheduled";
  // A new schedule starts tomorrow at nine.
  const [at, setAt] = useState<string | null>(
    scheduled && info.published_at
      ? info.published_at
      : dayjs().add(1, "day").hour(9).minute(0).second(0).format(),
  );
  const [expire, setExpire] = useState(!!info.unpublish_at);
  const [until, setUntil] = useState<string | null>(info.unpublish_at);
  const unpublishAt = unpublish && expire ? until : null;

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {t(
            scheduled
              ? "publishing.schedule.edit_title"
              : "publishing.schedule.title",
          )}
        </DialogTitle>
        <DialogDescription>
          {t("publishing.schedule.description", { name })}
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-5">
        <div className="space-y-2">
          <Label>{t("publishing.publish_on")}</Label>
          <DateTimeWidget
            field={REQUIRED}
            value={at}
            options={today()}
            onChange={setAt}
          />
        </div>
        {unpublish && (
          <>
            <div className="flex items-center justify-between">
              <Label htmlFor="publishing-expire">
                {t("publishing.schedule.unpublish_toggle")}
              </Label>
              <Switch
                id="publishing-expire"
                checked={expire}
                onCheckedChange={(checked) => {
                  setExpire(checked);

                  // A week later, to start from.
                  if (checked && !until && at) {
                    setUntil(dayjs(at).add(7, "day").format());
                  }
                }}
              />
            </div>
            {expire && (
              <div className="-mt-2">
                <DateTimeWidget
                  field={REQUIRED}
                  value={until}
                  options={today()}
                  onChange={setUntil}
                />
              </div>
            )}
          </>
        )}
        {at && (
          <div className="rounded-md bg-muted px-3 py-2.5 text-sm flex items-start gap-2">
            <PiClockBold className="mt-0.5 shrink-0 text-muted-foreground" />
            <span data-testid="schedule-summary">
              {unpublishAt
                ? t("publishing.schedule.summary_until", {
                    at: formatTime(at),
                    until: formatTime(unpublishAt),
                  })
                : t("publishing.schedule.summary", { at: formatTime(at) })}{" "}
              {t("publishing.time_zone", { zone: timeZone() })}
            </span>
          </div>
        )}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          isLoading={isPending}
          disabled={!at || (unpublish && expire && !until)}
          onClick={() => at && onSchedule(at, unpublishAt)}
        >
          {t("publishing.schedule.submit")}
        </Button>
      </DialogFooter>
    </>
  );
}

/** Set or remove the unpublish date of published content. */
export function UnpublishDateDialog({
  open,
  onOpenChange,
  name,
  info,
  isPending,
  onSubmit,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  name: string;
  info: PublishingInfo;
  isPending: boolean;
  onSubmit(unpublishAt: string | null): Promise<void>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {open && (
          <UnpublishDateForm
            name={name}
            info={info}
            isPending={isPending}
            onCancel={() => onOpenChange(false)}
            onSubmit={onSubmit}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function UnpublishDateForm({
  name,
  info,
  isPending,
  onCancel,
  onSubmit,
}: {
  name: string;
  info: PublishingInfo;
  isPending: boolean;
  onCancel(): void;
  onSubmit(unpublishAt: string | null): Promise<void>;
}) {
  const { t } = useTranslation();
  const [until, setUntil] = useState<string | null>(
    info.unpublish_at ??
      dayjs().add(7, "day").hour(9).minute(0).second(0).format(),
  );

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("publishing.unpublish_date.title")}</DialogTitle>
        <DialogDescription>
          {t("publishing.unpublish_date.description", { name })}
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-2">
        <Label>{t("publishing.unpublish_on")}</Label>
        <DateTimeWidget
          field={REQUIRED}
          value={until}
          options={today()}
          onChange={setUntil}
        />
        <p className="text-xs text-muted-foreground">
          {t("publishing.time_zone", { zone: timeZone() })}
        </p>
      </div>
      <DialogFooter className="sm:justify-between">
        {info.unpublish_at ? (
          <Button
            variant="ghost"
            className="text-destructive"
            disabled={isPending}
            onClick={() => onSubmit(null)}
          >
            {t("publishing.unpublish_date.remove")}
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button variant="outline" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button
            isLoading={isPending}
            disabled={!until}
            onClick={() => until && onSubmit(until)}
          >
            {t("common.save")}
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}
