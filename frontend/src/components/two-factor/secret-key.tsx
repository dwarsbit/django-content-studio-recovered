import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { PiCopyBold } from "react-icons/pi";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/** The secret in groups of four, for typing into an app by hand. */
export function SecretKey({ secret }: { secret: string }) {
  const { t } = useTranslation();
  const groups = secret.match(/.{1,4}/g) ?? [secret];

  return (
    <div className="flex items-center gap-1 rounded-md border bg-muted/50 py-1 pr-1 pl-3">
      <code className="min-w-0 flex-1 font-mono text-xs leading-5 tracking-wide whitespace-normal">
        {/* Breaks only between groups of four. */}
        {groups.map((group, index) => (
          <Fragment key={index}>
            {index > 0 && " "}
            <span className="whitespace-nowrap">{group}</span>
          </Fragment>
        ))}
      </code>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        className="shrink-0"
        aria-label={t("two_factor.copy_key")}
        onClick={async () => {
          await navigator.clipboard?.writeText(secret);
          toast.success(t("common.copied_to_clipboard"));
        }}
      >
        <PiCopyBold />
      </Button>
    </div>
  );
}
