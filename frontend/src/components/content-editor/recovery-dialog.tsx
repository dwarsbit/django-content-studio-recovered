import * as R from "ramda";
import { useContext, useState } from "react";
import { useFormContext } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Change } from "@/components/form-components/version-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { RecoveryOffer } from "@/hooks/use-recovery";
import { formatKeptAt } from "@/lib/recovery";
import type { Model } from "@/types";

import { EditorReadOnlyContext } from "./editor-read-only";

/**
 * Compare: the kept unsaved changes against the form as it is now, field
 * by field. A field someone else saved since (a clash) keeps the saved
 * value unless the editor picks theirs.
 */
export function RecoveryDialog({
  open,
  model,
  offer,
  savedBy,
  onRestore,
  onClose,
}: {
  open: boolean;
  model: Model;
  offer: RecoveryOffer;
  savedBy: string | null;
  onRestore(names: string[]): void;
  onClose(): void;
}) {
  const { t } = useTranslation();
  const form = useFormContext();
  const readOnly = useContext(EditorReadOnlyContext);
  const { kept, recovery, restored = [] } = offer;
  // Clashes first: they need a choice.
  const shown = [...recovery.clashes, ...recovery.clean].filter(
    (name) => !restored.includes(name),
  );
  // The clashes the editor takes their own value for.
  const [mine, setMine] = useState<string[]>([]);

  function close() {
    setMine([]);
    onClose();
  }

  const chosen = shown.filter(
    (name) => !recovery.clashes.includes(name) || mine.includes(name),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] grid-rows-[auto_minmax(0,1fr)_auto]">
        <DialogHeader>
          <DialogTitle>{t("recovery.dialog_title")}</DialogTitle>
          <DialogDescription>
            {t("recovery.dialog_description", {
              when: formatKeptAt(kept.keptAt),
              object: model.verbose_name,
            })}
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto scrollbar -mx-6 px-6">
          <dl className="divide-y" data-testid="recovery-fields">
            {shown.map((name) => {
              const field = model.fields[name];
              const clash = recovery.clashes.includes(name);
              const useMine = mine.includes(name);
              const label = field.verbose_name ?? name;

              return (
                <div key={name} className="py-3 first:pt-0">
                  <dt className="flex flex-wrap items-center gap-2 mb-1.5">
                    <span className="text-sm font-medium">
                      {label.charAt(0).toUpperCase() + label.slice(1)}
                    </span>
                    {clash && (
                      <Badge variant="outline" className="text-warning">
                        {savedBy
                          ? t("recovery.also_changed_by", { name: savedBy })
                          : t("recovery.also_changed")}
                      </Badge>
                    )}
                    {clash && !readOnly && (
                      <ToggleGroup
                        type="single"
                        size="sm"
                        variant="outline"
                        className="ml-auto"
                        value={useMine ? "mine" : "saved"}
                        onValueChange={(value) =>
                          value &&
                          setMine((names) =>
                            value === "mine"
                              ? R.union(names, [name])
                              : R.without([name], names),
                          )
                        }
                      >
                        <ToggleGroupItem value="saved" className="px-2.5">
                          {t("recovery.keep_saved")}
                        </ToggleGroupItem>
                        <ToggleGroupItem value="mine" className="px-2.5">
                          {t("recovery.use_mine")}
                        </ToggleGroupItem>
                      </ToggleGroup>
                    )}
                  </dt>
                  <dd className="min-w-0">
                    <Change
                      field={field}
                      before={form.getValues(name)}
                      after={kept.fields[name].value}
                    />
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={close}>
            {t("recovery.close")}
          </Button>
          {!readOnly && (
            <Button
              disabled={!chosen.length}
              onClick={() => {
                setMine([]);
                onRestore(chosen);
              }}
            >
              {t("recovery.restore_count", { count: chosen.length })}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
