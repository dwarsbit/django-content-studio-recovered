import { useTranslation } from "react-i18next";
import { PiDownloadSimpleBold } from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ExportFormat, ImportFormat } from "@/types";

/**
 * The export control: a button that downloads the only format, or a
 * menu of the formats (CSV, and Excel when the server can write it).
 * With importFormats, the menu also offers the list "For import": the
 * values as an import reads them back.
 */
export function ExportMenu({
  formats,
  onExport,
  importFormats = [],
  onExportForImport,
  label,
  icon,
  disabled,
  variant = "outline",
}: {
  formats: ExportFormat[];
  onExport(format: ExportFormat): void;
  importFormats?: ImportFormat[];
  onExportForImport?(format: ImportFormat): void;
  // Defaults to "Export".
  label?: string;
  // A Phosphor class; defaults to the download icon.
  icon?: string | null;
  disabled?: boolean;
  variant?: "outline" | "ghost";
}) {
  const { t } = useTranslation();
  const content = (
    <>
      {icon ? <span className={`${icon} text-sm`} /> : <PiDownloadSimpleBold />}
      {label ?? t("export.button")}
    </>
  );

  const forImport = onExportForImport ? importFormats : [];

  if (formats.length === 1 && forImport.length === 0) {
    return (
      <Button
        size="sm"
        variant={variant}
        disabled={disabled}
        title={t(`export.${formats[0]}`)}
        onClick={() => onExport(formats[0])}
      >
        {content}
      </Button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant={variant} disabled={disabled}>
          {content}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {formats.map((format) => (
          <DropdownMenuItem key={format} onSelect={() => onExport(format)}>
            {t(`export.${format}`)}
          </DropdownMenuItem>
        ))}
        {forImport.length > 0 && (
          <>
            {formats.length > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
              {t("export.for_import")}
            </DropdownMenuLabel>
            {forImport.map((format) => (
              <DropdownMenuItem
                key={`import-${format}`}
                onSelect={() => onExportForImport?.(format)}
              >
                {t(`export.${format}`)}
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
