import { type RefObject, useEffect, useRef } from "react";

import { isSaveShortcut } from "@/lib/shortcuts";

type Registration = {
  root: RefObject<HTMLElement | null>;
  save: RefObject<(() => void) | null>;
};

// The editors on screen, in the order they opened: a dialog editor
// opened over a page comes after it.
const editors: Registration[] = [];

// A modal dialog hides everything behind it (aria-hidden, or inert):
// the editor under it is out of reach, also for the shortcut.
function isReachable(element: HTMLElement | null) {
  return (
    !!element &&
    element.isConnected &&
    !element.closest('[aria-hidden="true"], [inert]')
  );
}

function onKeyDown(event: KeyboardEvent) {
  if (!isSaveShortcut(event) || editors.length === 0) {
    return;
  }

  // On an edit page the browser's "Save page" is never what is meant,
  // also while a confirm or another dialog covers the editor.
  event.preventDefault();

  if (event.repeat) {
    return;
  }

  const editor = [...editors]
    .reverse()
    .find(({ root }) => isReachable(root.current));

  editor?.save.current?.();
}

/**
 * Ctrl+S (⌘S on macOS) saves the editor from anywhere in the form. With
 * a dialog editor over a page, the dialog saves; a confirm or other
 * dialog over the editor takes the key from it. `save` is null where
 * the editor cannot save (read-only).
 */
export function useSaveShortcut(
  root: RefObject<HTMLElement | null>,
  save: (() => void) | null,
) {
  const saveRef = useRef(save);

  useEffect(() => {
    saveRef.current = save;
  });

  useEffect(() => {
    const registration = { root, save: saveRef };

    editors.push(registration);

    if (editors.length === 1) {
      window.addEventListener("keydown", onKeyDown);
    }

    return () => {
      editors.splice(editors.indexOf(registration), 1);

      if (editors.length === 0) {
        window.removeEventListener("keydown", onKeyDown);
      }
    };
  }, [root]);
}

/**
 * Saves like a click on Save: the focused field is blurred first, so
 * fields that commit on blur (a typed tag, a color) are part of the
 * save, and gets its focus back when the save gave it to nothing else
 * (an invalid field takes it). Rich text and code keep their focus:
 * they commit as you type.
 */
export async function saveFromKeyboard(save: () => Promise<void>) {
  const active =
    document.activeElement instanceof HTMLElement &&
    document.activeElement !== document.body &&
    !document.activeElement.isContentEditable
      ? document.activeElement
      : null;

  active?.blur();

  try {
    await save();
  } finally {
    if (
      active?.isConnected &&
      (document.activeElement === document.body || !document.activeElement)
    ) {
      active.focus({ preventScroll: true });
    }
  }
}
