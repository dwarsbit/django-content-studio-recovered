import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Card } from "@/components/analytics/parts";
import type { SaveMode } from "@/components/content-editor/save-button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  type ProfilePreferences,
  useUpdatePreferences,
} from "@/hooks/use-profile";
import { isMac } from "@/lib/shortcuts";
import { getErrorMessage } from "@/lib/utils";

const SAVE_ACTIONS: SaveMode[] = ["save", "add_another", "close"];

/**
 * The editor's preferences, saved as soon as one is picked: what the
 * edit page's Save button does.
 */
export function PreferencesCard({
  preferences,
}: {
  preferences: ProfilePreferences;
}) {
  const { t } = useTranslation();
  const { mutateAsync: save, isPending } = useUpdatePreferences();
  const value = preferences.save_action;

  return (
    <Card title={t("profile.preferences.title")}>
      <div className="border-t p-4 grid gap-3">
        <div>
          <div id="save-action-label" className="text-sm font-medium">
            {t("profile.preferences.save_action")}
          </div>
          <p className="text-sm text-muted-foreground">
            {t("profile.preferences.save_action_help", {
              shortcut: isMac() ? "⌘S" : "Ctrl S",
            })}
          </p>
        </div>
        <RadioGroup
          aria-labelledby="save-action-label"
          value={value}
          disabled={isPending}
          onValueChange={async (next) => {
            try {
              await save({ save_action: next as SaveMode });
              toast.success(t("profile.preferences.saved"));
            } catch (e: unknown) {
              toast.error(getErrorMessage(e));
            }
          }}
        >
          {SAVE_ACTIONS.map((action) => (
            <div key={action} className="flex items-start gap-2.5">
              <RadioGroupItem
                value={action}
                id={`save-action-${action}`}
                className="mt-0.5"
                aria-describedby={`save-action-${action}-help`}
              />
              <div className="grid gap-0.5">
                <Label htmlFor={`save-action-${action}`}>
                  {t(`profile.preferences.save_actions.${action}`)}
                </Label>
                <span
                  id={`save-action-${action}-help`}
                  className="text-sm text-muted-foreground"
                >
                  {t(`profile.preferences.save_actions.${action}_help`)}
                </span>
              </div>
            </div>
          ))}
        </RadioGroup>
      </div>
    </Card>
  );
}
