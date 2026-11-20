import type { NodeViewProps } from "@tiptap/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PiArrowsClockwiseBold,
  PiArrowsOutLineHorizontalBold,
  PiTextAlignCenterBold,
  PiTextAlignLeftBold,
  PiTrashBold,
} from "react-icons/pi";
import { toast } from "sonner";

import { SelectDialog } from "@/components/media-library/select-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { http } from "@/hooks/use-http";
import { getErrorMessage } from "@/lib/utils";
import type { MediaItem } from "@/types";

import {
  type ImageAlign,
  imageAttributes,
  type ImageOptions,
  imageSource,
  sizeLabel,
} from "../image-utils";

const ALIGN_ICONS = {
  left: PiTextAlignLeftBold,
  center: PiTextAlignCenterBold,
  wide: PiArrowsOutLineHorizontalBold,
} satisfies Record<ImageAlign, unknown>;

/**
 * The toolbar above a selected media library image: placement, size,
 * alt text, replace and remove.
 */
export function ImageToolbar({
  node,
  updateAttributes,
  deleteNode,
  options,
}: NodeViewProps & { options: ImageOptions }) {
  const { t } = useTranslation();
  const { align, size, alt, mediaId } = node.attrs;
  // The current size stays listed even when the widget no longer
  // offers it.
  const sizes = options.sizes.includes(size)
    ? options.sizes
    : [...options.sizes, size];

  async function changeSize(next: string) {
    try {
      const { data: item } = await http.get<MediaItem>(
        `/media-library/items/${mediaId}`,
      );
      updateAttributes({
        size: next,
        ...imageSource(item, next, options.metadataAttr),
      });
    } catch (e) {
      toast.error(getErrorMessage(e));
    }
  }

  return (
    <div
      contentEditable={false}
      className="rich-text-image-toolbar absolute -top-12 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 rounded-md border bg-popover text-popover-foreground p-1 shadow-md whitespace-nowrap"
      // Keep the image selected while using the toolbar.
      onMouseDown={(e) => {
        if (!(e.target as HTMLElement).closest("input")) {
          e.preventDefault();
        }
      }}
    >
      <ToggleGroup
        type="single"
        size="sm"
        value={align}
        onValueChange={(value) => value && updateAttributes({ align: value })}
      >
        {(["left", "center", "wide"] as const).map((value) => {
          const Icon = ALIGN_ICONS[value];
          const label = t(`widgets.rich_text_widget.align_${value}`);

          // No tooltip: its trigger would replace the item's data-state.
          return (
            <ToggleGroupItem
              key={value}
              value={value}
              aria-label={label}
              title={label}
            >
              <Icon />
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>

      {sizes.length > 1 && (
        <>
          <Separator orientation="vertical" className="h-6!" />
          <Select value={size} onValueChange={changeSize}>
            <SelectTrigger
              size="sm"
              aria-label={t("widgets.rich_text_widget.image_size")}
              className="w-[120px] border-0 shadow-none"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sizes.map((value) => (
                <SelectItem key={value} value={value}>
                  {sizeLabel(value, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </>
      )}

      <Separator orientation="vertical" className="h-6!" />
      <AltTextButton
        value={alt}
        onChange={(value) => updateAttributes({ alt: value })}
      />

      {options.canPick && (
        <SelectDialog
          multiple={false}
          type="image"
          onSelect={(item) =>
            updateAttributes(
              imageAttributes(item as MediaItem, size, options.metadataAttr),
            )
          }
        >
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("widgets.rich_text_widget.replace_image")}
            title={t("widgets.rich_text_widget.replace_image")}
          >
            <PiArrowsClockwiseBold />
          </Button>
        </SelectDialog>
      )}
      <Button
        size="sm"
        variant="ghost"
        aria-label={t("widgets.rich_text_widget.remove_image")}
        title={t("widgets.rich_text_widget.remove_image")}
        onClick={() => deleteNode()}
      >
        <PiTrashBold />
      </Button>
    </div>
  );
}

function AltTextButton({
  value,
  onChange,
}: {
  value: string;
  onChange(value: string): void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setDraft(value);
        }
        setOpen(next);
      }}
    >
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost">
          {t("widgets.rich_text_widget.alt_text")}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="center">
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onChange(draft.trim());
            setOpen(false);
          }}
        >
          <Label htmlFor="rich-text-alt">
            {t("widgets.rich_text_widget.alt_text")}
          </Label>
          <Input
            id="rich-text-alt"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            {t("widgets.rich_text_widget.alt_text_help")}
          </p>
          <div className="flex justify-end">
            <Button size="sm" type="submit">
              {t("common.save")}
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
