import "./rich-text.css";

import type { Editor } from "@tiptap/core";
import { Image } from "@tiptap/extension-image";
import { Link } from "@tiptap/extension-link";
import { TableCell, TableHeader, TableKit } from "@tiptap/extension-table";
import { Typography } from "@tiptap/extension-typography";
import { Tiptap, useEditor } from "@tiptap/react";
import { StarterKit } from "@tiptap/starter-kit";
import * as R from "ramda";
import { useEffect, useMemo, useRef, useState } from "react";

import { useDiscover } from "@/hooks/use-discover";
import { useUpload } from "@/hooks/use-upload";
import type {
  HeadingLevel,
  MediaItem,
  RichTextFeature,
  RichTextWidgetOptions,
} from "@/types";

import { FormattingMenu } from "./components/formatting-menu";
import { LinkMenu } from "./components/link-button";
import { LinkDialog } from "./components/link-dialog";
import { TableMenu } from "./components/table-menu";
import { MediaImage } from "./extensions/media-image";
import {
  imageAttributes,
  type ImageOptions,
  ImageOptionsContext,
  ORIGINAL_SIZE,
} from "./image-utils";

const ALL_FEATURES: RichTextFeature[] = [
  "heading",
  "blockquote",
  "code_block",
  "bold",
  "italic",
  "underline",
  "strike",
  "ordered_list",
  "bullet_list",
  "link",
  "image",
  "table",
];

const ALL_HEADING_LEVELS: HeadingLevel[] = [1, 2, 3, 4, 5, 6];

/**
 * A link that may point to an object in the studio: its model and id
 * are kept next to the URL (data-link-model, data-link-id), so the site
 * can refresh the URL when it renders the HTML.
 */
const StudioLink = Link.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      linkModel: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-link-model"),
        renderHTML: (attrs) =>
          attrs.linkModel ? { "data-link-model": attrs.linkModel } : {},
      },
      linkId: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-link-id"),
        renderHTML: (attrs) =>
          attrs.linkId ? { "data-link-id": attrs.linkId } : {},
      },
    };
  },
});

/**
 * The editor's extensions for the given features. A feature left out
 * is left out of the editor's schema too, so pasted text loses it.
 * Without a feature list, the editor has everything, including the
 * extras that have no toolbar button (inline code, rules).
 */
function getExtensions(
  features: RichTextFeature[] | undefined,
  headingLevels: HeadingLevel[],
) {
  const has = (feature: RichTextFeature) =>
    !features || features.includes(feature);
  const hasLists = has("ordered_list") || has("bullet_list");
  // Table cells hold text and lists: no images or tables.
  const cellContent = [
    "paragraph",
    ...(has("bullet_list") ? ["bulletList"] : []),
    ...(has("ordered_list") ? ["orderedList"] : []),
  ].join(" | ");

  return [
    StarterKit.configure({
      heading: has("heading") ? { levels: headingLevels } : false,
      blockquote: has("blockquote") ? {} : false,
      codeBlock: has("code_block") ? {} : false,
      bold: has("bold") ? {} : false,
      italic: has("italic") ? {} : false,
      underline: has("underline") ? {} : false,
      strike: has("strike") ? {} : false,
      orderedList: has("ordered_list") ? {} : false,
      bulletList: has("bullet_list") ? {} : false,
      listItem: hasLists ? {} : false,
      listKeymap: hasLists ? {} : false,
      link: false,
      code: features ? false : {},
      horizontalRule: features ? false : {},
    }),
    Typography,
    ...(has("link")
      ? [
          StudioLink.configure({
            autolink: true,
            linkOnPaste: true,
            openOnClick: false,
            // "Open in a new tab" in the link dialog sets the target.
            HTMLAttributes: { target: null, rel: null },
          }),
        ]
      : []),
    ...(has("image")
      ? [
          MediaImage,
          // Images that are not from the media library, such as pasted
          // ones, stay as they are.
          Image.configure({ HTMLAttributes: { class: "rich-text-image" } }),
        ]
      : []),
    ...(has("table")
      ? [
          TableKit.configure({
            table: { resizable: false },
            tableCell: false,
            tableHeader: false,
          }),
          TableCell.extend({
            content: `(${cellContent})+`,
            addAttributes: withoutDefaultSpans,
          }),
          TableHeader.extend({
            content: `(${cellContent})+`,
            addAttributes: withoutDefaultSpans,
          }),
        ]
      : []),
  ];
}

/**
 * A table cell's attributes, without colspan="1" and rowspan="1" in
 * the HTML: cells span one row and column unless they say otherwise.
 */
function withoutDefaultSpans(this: {
  parent?: () => Record<string, Record<string, unknown>>;
}) {
  const attributes = this.parent?.() ?? {};

  return {
    ...attributes,
    colspan: {
      ...attributes.colspan,
      renderHTML: (attrs: Record<string, number>) =>
        attrs.colspan > 1 ? { colspan: attrs.colspan } : {},
    },
    rowspan: {
      ...attributes.rowspan,
      renderHTML: (attrs: Record<string, number>) =>
        attrs.rowspan > 1 ? { rowspan: attrs.rowspan } : {},
    },
  };
}

/** The image files among a paste or drop. */
function imageFiles(data: DataTransfer | null): File[] {
  return Array.from(data?.files ?? []).filter((file) =>
    file.type.startsWith("image/"),
  );
}

export function RichTextWidget({
  value,
  onChange,
  disabled,
  options = {},
}: RichtTextProps) {
  const { data: discover } = useDiscover();
  const features = options.features ?? ALL_FEATURES;
  const headingLevels = options.heading_levels ?? ALL_HEADING_LEVELS;
  const mediaLibrary = discover?.media_library;
  const canPickImages = features.includes("image") && !!mediaLibrary?.enabled;
  const imageOptions = useMemo<ImageOptions>(() => {
    const known = mediaLibrary?.image_sizes ?? [];
    const sizes = options.image_sizes
      ? options.image_sizes.filter(
          (size) => size === ORIGINAL_SIZE || known.includes(size),
        )
      : [ORIGINAL_SIZE, ...known];

    return {
      sizes: R.isEmpty(sizes) ? [ORIGINAL_SIZE] : sizes,
      canPick: canPickImages,
      metadataAttr: mediaLibrary?.metadata ?? null,
    };
  }, [mediaLibrary, options.image_sizes, canPickImages]);
  const models = useMemo(() => discover?.models ?? [], [discover]);
  const linkModels = useMemo(
    () =>
      models.filter(
        (model) =>
          model.admin.linkable &&
          !model.inline_only &&
          (!options.link_models || options.link_models.includes(model.label)),
      ),
    [models, options.link_models],
  );
  const [linkDialog, setLinkDialog] = useState(false);
  const upload = useUpload();

  // Pasted and dropped image files go to the media library; the
  // editor's handlers are created once, so they read the latest state.
  const pasteRef = useRef<
    (editor: Editor, files: File[], pos?: number) => void
  >(() => {});
  const canPasteRef = useRef(false);

  useEffect(() => {
    canPasteRef.current = canPickImages;
    pasteRef.current = (editor, files, pos) => {
      void (async () => {
        const items = (await upload(files)).filter(
          (item): item is MediaItem => !R.isNil(item) && item.type === "image",
        );

        if (R.isEmpty(items)) {
          return;
        }

        const content = items.map((item) => ({
          type: "mediaImage",
          attrs: imageAttributes(
            item,
            imageOptions.sizes[0],
            imageOptions.metadataAttr,
          ),
        }));
        const chain = editor.chain().focus();

        (pos === undefined
          ? chain.insertContent(content)
          : chain.insertContentAt(pos, content)
        ).run();
      })();
    };
  }, [canPickImages, imageOptions, upload]);

  // The editor is created once; its extensions follow the options it
  // was created with.
  const [extensions] = useState(() =>
    getExtensions(options.features, headingLevels),
  );
  const editor = useEditor({
    extensions,
    content: value ?? "",
    editable: !disabled,
    editorProps: {
      attributes: {
        class: "rich-text-field",
      },
      handlePaste(_view, event) {
        const files = imageFiles(event.clipboardData);

        if (!canPasteRef.current || R.isEmpty(files)) {
          return false;
        }

        pasteRef.current(editor, files);
        return true;
      },
      handleDrop(view, event, _slice, moved) {
        const files = imageFiles(event.dataTransfer);

        if (moved || !canPasteRef.current || R.isEmpty(files)) {
          return false;
        }

        const pos = view.posAtCoords({
          left: event.clientX,
          top: event.clientY,
        })?.pos;

        event.preventDefault();
        pasteRef.current(editor, files, pos);
        return true;
      },
    },
    onUpdate({ editor }) {
      onChange?.(editor.getHTML());
    },
  });
  /*
   * Update editor state if it doesn't match
   * the current value.
   */
  useEffect(() => {
    if (value !== editor.getHTML()) {
      editor.commands.setContent(value ?? "");
    }
  }, [value, editor]);

  return (
    <Tiptap editor={editor}>
      <ImageOptionsContext.Provider value={imageOptions}>
        <div className="border border-solid rounded-md bg-background focus-within:border-ring">
          <FormattingMenu
            features={features.filter(
              (feature) => feature !== "image" || canPickImages,
            )}
            headingLevels={headingLevels}
            onLink={() => setLinkDialog(true)}
          />
          <div className="max-h-[600px] overflow-y-auto scrollbar">
            <Tiptap.Content />
          </div>
          {features.includes("table") && <TableMenu editor={editor} />}
          {features.includes("link") && (
            <LinkMenu
              editor={editor}
              models={models}
              onEdit={() => setLinkDialog(true)}
            />
          )}
          {linkDialog && (
            <LinkDialog
              editor={editor}
              linkModels={linkModels}
              onClose={() => setLinkDialog(false)}
            />
          )}
        </div>
      </ImageOptionsContext.Provider>
    </Tiptap>
  );
}

interface RichtTextProps {
  value?: string | null;
  onChange?(value: string): void;
  disabled?: boolean;
  options?: RichTextWidgetOptions;
}
