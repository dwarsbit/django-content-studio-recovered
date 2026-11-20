// Keyboard shortcuts use ⌘ on macOS and Ctrl elsewhere.
export function isMac() {
  return (
    typeof navigator !== "undefined" &&
    navigator.platform.toUpperCase().includes("MAC")
  );
}

// ⌘S on macOS, Ctrl+S elsewhere (either modifier works on both, like
// ⌘K). Shift and Alt combinations are left to the browser.
export function isSaveShortcut(event: KeyboardEvent) {
  return (
    (event.metaKey || event.ctrlKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === "s"
  );
}
