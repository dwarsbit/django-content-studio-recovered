import type { Editor } from "@tiptap/core";
import { useEditorState, useTiptap } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import { useTranslation } from "react-i18next";
import {
  PiArrowSquareOutBold,
  PiGlobeBold,
  PiLinkBold,
  PiLinkBreakBold,
  PiPencilSimpleBold,
} from "react-icons/pi";
import { useHref } from "react-router";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Model } from "@/types";

export function LinkButton({ onClick }: { onClick: VoidFunction }) {
  const { t } = useTranslation();
  const { editor } = useTiptap();
  const isLink = useEditorState({
    editor,
    selector: ({ editor }) => editor.isActive("link"),
  });
  const label = isLink
    ? t("widgets.rich_text_widget.update_link")
    : t("widgets.rich_text_widget.set_link");

  return (
    <Tooltip>
      <TooltipContent>{label}</TooltipContent>
      <TooltipTrigger asChild>
        <Button size="sm" variant="ghost" aria-label={label} onClick={onClick}>
          <PiLinkBold />
        </Button>
      </TooltipTrigger>
    </Tooltip>
  );
}

/**
 * The bubble under the link the cursor is in: where it goes (the model
 * and address of a link to an object), open, edit and remove.
 */
export function LinkMenu({
  editor,
  models,
  onEdit,
}: {
  editor: Editor;
  // Every model of the discover, to name a linked object's model.
  models: Model[];
  onEdit: VoidFunction;
}) {
  const { t } = useTranslation();
  const attrs = useEditorState({
    editor,
    selector: ({ editor }) => {
      const { href, linkModel, linkId } = editor.getAttributes("link");

      return { href, linkModel, linkId } as {
        href?: string;
        linkModel?: string | null;
        linkId?: string | null;
      };
    },
  });
  const model = attrs.linkModel
    ? models.find((m) => m.label === attrs.linkModel)
    : undefined;
  // A link to an object opens the object in the studio.
  const studioHref = useHref(
    model && attrs.linkId ? `/content/${model.label}/${attrs.linkId}` : "/",
  );
  const openHref = model && attrs.linkId ? studioHref : attrs.href;

  return (
    <BubbleMenu
      editor={editor}
      pluginKey="linkMenu"
      shouldShow={({ editor, state, view, element }) =>
        editor.isEditable &&
        state.selection.empty &&
        editor.isActive("link") &&
        (view.hasFocus() || element.contains(document.activeElement))
      }
      options={{ placement: "bottom-start", offset: 6 }}
    >
      <div className="rich-text-link-menu flex items-center gap-1 rounded-md border bg-popover text-popover-foreground p-1 pl-3 shadow-md text-sm">
        {model?.admin.icon ? (
          <span className={cn(model.admin.icon, "text-muted-foreground")} />
        ) : (
          <PiGlobeBold className="text-muted-foreground shrink-0" />
        )}
        <span className="max-w-[320px] truncate">
          {model && (
            <span className="text-muted-foreground">
              {model.verbose_name.charAt(0).toUpperCase() +
                model.verbose_name.slice(1)}{" "}
              ·{" "}
            </span>
          )}
          {attrs.href}
        </span>
        {openHref && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-2"
            asChild
            aria-label={t("widgets.rich_text_widget.open_link")}
            title={t("widgets.rich_text_widget.open_link")}
          >
            <a href={openHref} target="_blank" rel="noreferrer">
              <PiArrowSquareOutBold />
            </a>
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          aria-label={t("widgets.rich_text_widget.update_link")}
          title={t("widgets.rich_text_widget.update_link")}
          onClick={onEdit}
        >
          <PiPencilSimpleBold />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          aria-label={t("widgets.rich_text_widget.remove_link")}
          title={t("widgets.rich_text_widget.remove_link")}
          onClick={() =>
            editor.chain().focus().extendMarkRange("link").unsetLink().run()
          }
        >
          <PiLinkBreakBold />
        </Button>
      </div>
    </BubbleMenu>
  );
}
