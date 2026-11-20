import {
  NodeViewContent,
  type NodeViewProps,
  NodeViewWrapper,
  useEditorState,
} from "@tiptap/react";
import { useContext } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { ImageOptionsContext } from "../image-utils";
import { ImageToolbar } from "./image-toolbar";

export function MediaImageView(props: NodeViewProps) {
  const { node, editor, getPos, selected } = props;
  const { t } = useTranslation();
  const options = useContext(ImageOptionsContext);
  const { src, alt, align, width, height } = node.attrs;
  // The toolbar shows while the image or its caption is selected.
  const active = useEditorState({
    editor,
    selector: ({ editor }) => {
      const pos = getPos();

      if (typeof pos !== "number" || !editor.isEditable) {
        return false;
      }

      const { from, to } = editor.state.selection;

      return from >= pos && to <= pos + node.nodeSize;
    },
  });

  return (
    <NodeViewWrapper
      as="figure"
      className={cn(
        "rich-text-figure",
        `align-${align}`,
        selected && "is-selected",
      )}
    >
      {(active || selected) && editor.isEditable && (
        <ImageToolbar {...props} options={options} />
      )}
      <img
        src={src}
        alt={alt}
        width={width ?? undefined}
        height={height ?? undefined}
        draggable={false}
        data-drag-handle
        // Clicking the image selects it, which shows its toolbar.
        onClick={() => {
          const pos = getPos();

          if (typeof pos === "number" && editor.isEditable) {
            editor.chain().focus().setNodeSelection(pos).run();
          }
        }}
      />
      <NodeViewContent
        as="div"
        className={cn("figcaption", node.content.size === 0 && "is-empty")}
        data-placeholder={
          editor.isEditable
            ? t("widgets.rich_text_widget.caption_placeholder")
            : undefined
        }
      />
    </NodeViewWrapper>
  );
}
