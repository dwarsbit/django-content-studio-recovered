import { useTranslation } from "react-i18next";
import { PiCopyBold, PiDownloadSimpleBold } from "react-icons/pi";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/**
 * The recovery codes, shown once: a grid to read, with buttons to copy
 * them or save them as a text file.
 */
export function RecoveryCodes({
  codes,
  fileName = "recovery-codes.txt",
}: {
  codes: string[];
  fileName?: string;
}) {
  const { t } = useTranslation();
  const text = codes.join("\n");

  return (
    <div className="flex flex-col gap-3">
      <ol className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-lg border bg-muted/50 px-5 py-4 font-mono text-sm tabular-nums">
        {codes.map((code) => (
          <li key={code} className="tracking-wide">
            {code}
          </li>
        ))}
      </ol>
      <div className="grid grid-cols-2 gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={async () => {
            await navigator.clipboard?.writeText(text);
            toast.success(t("common.copied_to_clipboard"));
          }}
        >
          <PiCopyBold />
          {t("two_factor.copy_codes")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            const url = URL.createObjectURL(
              new Blob([text + "\n"], { type: "text/plain" }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = fileName;
            link.click();
            URL.revokeObjectURL(url);
          }}
        >
          <PiDownloadSimpleBold />
          {t("common.download")}
        </Button>
      </div>
    </div>
  );
}
