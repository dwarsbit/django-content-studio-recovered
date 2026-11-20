import { useTiptap } from "@tiptap/react";
import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { PiImageBold } from "react-icons/pi";

import { SelectDialog } from "@/components/media-library/select-dialog";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { MediaItem } from "@/types";

import { imageAttributes, ImageOptionsContext } from "../image-utils";

/** Inserts an image from the media library at the cursor. */
export function ImageButton() {
  const { t } = useTranslation();
  const { editor } = useTiptap();
  const options = useContext(ImageOptionsContext);
  const label = t("widgets.rich_text_widget.insert_image");

  return (
    <Tooltip>
      <TooltipContent>{label}</TooltipContent>
      <SelectDialog
        multiple={false}
        type="image"
        onSelect={(item) =>
          editor
            .chain()
            .focus()
            .insertContent({
              type: "mediaImage",
              attrs: imageAttributes(
                item as MediaItem,
                options.sizes[0],
                options.metadataAttr,
              ),
            })
            .run()
        }
      >
        <TooltipTrigger asChild>
          <Button size="sm" variant="ghost" aria-label={label}>
            <PiImageBold />
          </Button>
        </TooltipTrigger>
      </SelectDialog>
    </Tooltip>
  );
}
