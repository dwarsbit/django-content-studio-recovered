import { createContext } from "react";

import type { MediaItem, MediaMetadata } from "@/types";

export type ImageAlign = "left" | "center" | "wide";

export const ORIGINAL_SIZE = "original";

/**
 * What the image toolbar offers: the sizes an image can have (the
 * first being the default) and whether the media library can be
 * opened to replace an image.
 */
export interface ImageOptions {
  sizes: string[];
  canPick: boolean;
  // The media item attribute holding width and height (discover).
  metadataAttr: string | null;
}

export const ImageOptionsContext = createContext<ImageOptions>({
  sizes: [ORIGINAL_SIZE],
  canPick: false,
  metadataAttr: null,
});

/**
 * A URL on the admin's own host as a path: the admin's address is not
 * necessarily the site's, so stored HTML should not depend on it.
 */
function sameOrigin(url: string): string {
  const origin = window.location.origin;

  return url.startsWith(`${origin}/`) ? url.slice(origin.length) : url;
}

/**
 * The src, width and height of a media library image in a size of
 * IMAGE_SIZES, or of its own file for "original" or a size it does
 * not have.
 */
export function imageSource(
  item: MediaItem,
  size: string,
  metadataAttr: string | null = null,
) {
  const entry = size === ORIGINAL_SIZE ? undefined : item.sizes?.[size];

  if (entry) {
    return {
      src: sameOrigin(entry.url),
      width: entry.width,
      height: entry.height,
    };
  }

  const metadata = metadataAttr
    ? ((item as unknown as Record<string, unknown>)[metadataAttr] as
        MediaMetadata | null | undefined)
    : undefined;

  return {
    src: sameOrigin(item.file),
    width: (metadata?.width as number | undefined) ?? null,
    height: (metadata?.height as number | undefined) ?? null,
  };
}

/** The attributes of a media library image node for an item. */
export function imageAttributes(
  item: MediaItem,
  size: string,
  metadataAttr: string | null = null,
) {
  return {
    mediaId: String(item.id),
    alt: item.alt_text ?? "",
    size,
    ...imageSource(item, size, metadataAttr),
  };
}

/** A size's label: "original" translated, others as named. */
export function sizeLabel(size: string, t: (key: string) => string) {
  return size === ORIGINAL_SIZE
    ? t("widgets.rich_text_widget.size_original")
    : size.charAt(0).toUpperCase() + size.slice(1).replace(/[_-]/g, " ");
}
