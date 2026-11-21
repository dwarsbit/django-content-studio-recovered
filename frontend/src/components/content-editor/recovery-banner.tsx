import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import * as R from "ramda";
import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import { PiClockCounterClockwiseBold, PiWarningBold } from "react-icons/pi";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useHttp } from "@/hooks/use-http";
import type { RecoveryOffer } from "@/hooks/use-recovery";
import { formatKeptAt } from "@/lib/recovery";
import type { ActivityLogEntry, Model } from "@/types";

import { EditorReadOnlyContext } from "./editor-read-only";
import { RecoveryDialog } from "./recovery-dialog";

/** The fields' names as a sentence: "Title, Lead and Body". */
function useFieldList(model: Model) {
  const { t } = useTranslation();

  return (names: string[]) => {
    const labels = names.map((name) => {
      const label = model.fields[name]?.verbose_name ?? name;
      return label.charAt(0).toUpperCase() + label.slice(1);
    });

    return labels.length < 2
      ? (labels[0] ?? "")
      : t("recovery.list", {
          items: labels.slice(0, -1).join(", "),
          last: labels.at(-1),
        });
  };
}

/**
 * Above the form: unsaved changes kept in this browser earlier, with
 * Restore unsaved changes, Compare and Discard. Nothing changes until
 * the editor picks one.
 */
export function RecoveryBanner({
  model,
  resourcePath,
  objectId,
  offer,
  onRestore,
  onDiscard,
}: {
  model: Model;
  resourcePath: string;
  objectId?: string | null;
  offer: RecoveryOffer;
  onRestore(names: string[]): void;
  onDiscard(): void;
}) {
  const { t } = useTranslation();
  const http = useHttp();
  const readOnly = useContext(EditorReadOnlyContext);
  const fieldList = useFieldList(model);
  const [comparing, setComparing] = useState(false);
  const { kept, recovery, restored } = offer;
  const { clean, clashes, changedSince } = recovery;
  const isCreate = R.isNil(objectId);
  const when = formatKeptAt(kept.keptAt);
  const object = model.verbose_name;

  // Who saved the object after the changes were kept: the newest change
  // in its activity since then (the Activity card shares the request).
  const { data: activity } = useQuery({
    enabled: changedSince && !isCreate,
    retry: false,
    queryKey: ["activity", model.label, objectId, resourcePath],
    async queryFn() {
      const { data } = await http.get<ActivityLogEntry[]>(
        `${resourcePath}/${objectId}/activity`,
      );
      return data;
    },
  });
  const savedBy =
    activity?.find((entry) => dayjs(entry.action_time).valueOf() > kept.keptAt)
      ?.user?.__str__ ?? null;
  const left = clashes.filter((name) => !restored?.includes(name));

  let title: string;
  let description: string;

  if (restored) {
    title = t("recovery.restored_title", { count: restored.length });
    description = t(
      savedBy ? "recovery.restored_clash_by" : "recovery.restored_clash",
      { fields: fieldList(left), name: savedBy, count: left.length },
    );
  } else if (clashes.length) {
    title = t(savedBy ? "recovery.clash_title_by" : "recovery.clash_title", {
      name: savedBy,
      object,
    });
    description = [
      t("recovery.clash_fields", {
        fields: fieldList(clashes),
        count: clashes.length,
      }),
      clean.length
        ? t("recovery.clash_clean", { count: clean.length, when })
        : t("recovery.clash_none", { when }),
    ].join(" ");
  } else if (isCreate) {
    title = t("recovery.create_title", { object, when });
    description = t("recovery.create_description", {
      fields: fieldList(clean),
    });
  } else {
    title = t("recovery.title", { when });
    description = [
      t("recovery.description", {
        count: clean.length,
        fields: fieldList(clean),
      }),
      changedSince ? t("recovery.changed_since", { object }) : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  const warn = clashes.length > 0;

  return (
    <>
      <Alert
        variant={warn ? "warning" : "default"}
        className="mb-6"
        data-testid="recovery-banner"
      >
        {warn ? <PiWarningBold /> : <PiClockCounterClockwiseBold />}
        <AlertTitle className="line-clamp-none">{title}</AlertTitle>
        <AlertDescription>
          <p>{description}</p>
          <div className="flex flex-wrap gap-2 mt-2">
            {!restored && !readOnly && (
              <Button
                size="sm"
                onClick={() => onRestore(clean)}
                disabled={!clean.length}
              >
                {t("recovery.restore")}
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setComparing(true)}
            >
              {t("recovery.compare")}
            </Button>
            <Button size="sm" variant="ghost" onClick={onDiscard}>
              {restored ? t("recovery.dismiss") : t("recovery.discard")}
            </Button>
          </div>
        </AlertDescription>
      </Alert>
      <RecoveryDialog
        open={comparing}
        model={model}
        offer={offer}
        savedBy={savedBy}
        onRestore={(names) => {
          setComparing(false);
          onRestore(names);
        }}
        onClose={() => setComparing(false)}
      />
    </>
  );
}
