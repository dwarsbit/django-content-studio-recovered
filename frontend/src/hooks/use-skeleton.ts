import { useEffect, useRef, useState } from "react";

// A load quicker than this shows no skeleton at all: the page goes
// straight to its content instead of flashing a placeholder.
export const SKELETON_DELAY = 200;
// Once a skeleton shows, it stays at least this long, so it does not
// blink away the moment it appeared.
export const SKELETON_MIN_DURATION = 300;

/**
 * Whether to show a loading skeleton for something that is `loading`.
 * The skeleton appears only after SKELETON_DELAY and then stays at
 * least SKELETON_MIN_DURATION, also when the data arrives sooner.
 */
export function useSkeleton(
  loading: boolean,
  {
    delay = SKELETON_DELAY,
    minDuration = SKELETON_MIN_DURATION,
  }: { delay?: number; minDuration?: number } = {},
) {
  const [shown, setShown] = useState(false);
  const shownAt = useRef(0);

  useEffect(() => {
    if (loading === shown) {
      return;
    }

    const wait = loading
      ? delay
      : Math.max(0, minDuration - (Date.now() - shownAt.current));
    const timeoutId = setTimeout(() => {
      shownAt.current = Date.now();
      setShown(loading);
    }, wait);

    return () => clearTimeout(timeoutId);
  }, [loading, shown, delay, minDuration]);

  return shown;
}
