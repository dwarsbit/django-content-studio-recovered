import { useTranslation } from "react-i18next";
import {
  PiDotsThreeBold,
  PiDownloadSimpleBold,
  PiUploadSimpleBold,
} from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ExportFormat, ImportFormat } from "@/types";

/**
 * The ⋯ menu next to Create on a list page: import from a file, export
 * the list, and export it "for import" (raw values an import reads
 * back). Each export offers its formats in a submenu.
 */
export function ListActionsMenu({
  exportFormats,
  onExport,
  importFormats = [],
  onExportForImport,
  onImport,
  disabled,
}: {
  exportFormats: ExportFormat[];
  onExport(format: ExportFormat): void;
  importFormats?: ImportFormat[];
  onExportForImport?(format: ImportFormat): void;
  // Opens the import dialog; left out when the user cannot import.
  onImport?(): void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const forImport = onExportForImport ? importFormats : [];

  if (!onImport && exportFormats.length === 0 && forImport.length === 0) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          disabled={disabled}
          aria-label={t("list_view.more_actions")}
          title={t("list_view.more_actions")}
        >
          <PiDotsThreeBold />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-48">
        {onImport && (
          <DropdownMenuItem onSelect={onImport} className="justify-start">
            <PiUploadSimpleBold />
            {t("import.from_file")}
          </DropdownMenuItem>
        )}
        <FormatsSubmenu
          label={t("export.button")}
          formats={exportFormats}
          onSelect={onExport}
        />
        <FormatsSubmenu
          label={t("export.for_import")}
          formats={forImport}
          onSelect={(format) => onExportForImport?.(format)}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function FormatsSubmenu<Format extends string>({
  label,
  formats,
  onSelect,
}: {
  label: string;
  formats: Format[];
  onSelect(format: Format): void;
}) {
  const { t } = useTranslation();

  if (formats.length === 0) {
    return null;
  }

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="gap-2 p-1">
        <PiDownloadSimpleBold className="size-4 text-muted-foreground" />
        {label}
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent>
        {formats.map((format) => (
          <DropdownMenuItem key={format} onSelect={() => onSelect(format)}>
            {t(`export.${format}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
