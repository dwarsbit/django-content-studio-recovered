import { mergeAttributes, Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { MediaImageView } from "../components/media-image-view";
import { ORIGINAL_SIZE } from "../image-utils";

const imageOf = (element: HTMLElement) =>
  element.querySelector<HTMLImageElement>("img[data-media-id]");

const numberOf = (value: string | null | undefined) =>
  value && /^\d+$/.test(value) ? Number(value) : null;

/**
 * An image from the media library: a figure with the image and an
 * editable caption. The media item's id and size are kept next to the
 * URL, so the site can refresh the URL when it renders the HTML:
 *
 *   <figure class="rich-text-figure align-center">
 *     <img src="…" alt="…" width="…" height="…" data-media-id="7" data-size="hero">
 *     <figcaption>…</figcaption>
 *   </figure>
 */
export const MediaImage = Node.create({
  name: "mediaImage",
  group: "block",
  content: "inline*",
  marks: "",
  draggable: true,
  isolating: true,
  defining: true,

  addAttributes() {
    return {
      mediaId: {
        default: null,
        parseHTML: (el) => imageOf(el)?.getAttribute("data-media-id"),
      },
      src: {
        default: null,
        parseHTML: (el) => imageOf(el)?.getAttribute("src"),
      },
      alt: {
        default: "",
        parseHTML: (el) => imageOf(el)?.getAttribute("alt") ?? "",
      },
      width: {
        default: null,
        parseHTML: (el) => numberOf(imageOf(el)?.getAttribute("width")),
      },
      height: {
        default: null,
        parseHTML: (el) => numberOf(imageOf(el)?.getAttribute("height")),
      },
      size: {
        default: ORIGINAL_SIZE,
        parseHTML: (el) =>
          imageOf(el)?.getAttribute("data-size") || ORIGINAL_SIZE,
      },
      align: {
        default: "center",
        parseHTML: (el) =>
          (["left", "center", "wide"] as const).find((align) =>
            el.classList.contains(`align-${align}`),
          ) ?? "center",
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "figure",
        contentElement: "figcaption",
        getAttrs: (el) => (imageOf(el as HTMLElement) ? null : false),
      },
    ];
  },

  renderHTML({ node }) {
    const { mediaId, src, alt, width, height, size, align } = node.attrs;

    return [
      "figure",
      { class: `rich-text-figure align-${align}` },
      [
        "img",
        mergeAttributes(
          { src, alt },
          width && height ? { width, height } : {},
          { "data-media-id": mediaId, "data-size": size },
        ),
      ],
      ["figcaption", 0],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(MediaImageView);
  },
});
