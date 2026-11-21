import { useTranslation } from "react-i18next";

import { Change } from "@/components/form-components/version-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Model, Resource } from "@/types";

function capfirst(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Compare, from the Publishing card: the published values of the
 * fields with unpublished changes next to the changes, field by field.
 */
export function CompareDialog({
  open,
  onOpenChange,
  model,
  resource,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  model: Model;
  resource: Resource;
}) {
  const { t } = useTranslation();
  const pending = resource.__publishing__?.pending;
  const fields = (pending?.fields ?? []).filter((name) => model.fields[name]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] grid-rows-[auto_minmax(0,1fr)_auto]">
        <DialogHeader>
          <DialogTitle>{t("publishing.changes.compare_title")}</DialogTitle>
          <DialogDescription>
            {t("publishing.changes.compare_description")}
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto scrollbar -mx-6 px-6">
          <dl className="divide-y" data-testid="compare-fields">
            {fields.map((name) => (
              <div key={name} className="py-3 first:pt-0">
                <dt className="text-sm font-medium mb-1.5">
                  {capfirst(model.fields[name].verbose_name ?? name)}
                </dt>
                <dd className="min-w-0">
                  <Change
                    field={model.fields[name]}
                    before={pending?.live[name]}
                    after={resource[name]}
                  />
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("history.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
