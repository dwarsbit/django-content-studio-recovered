import dayjs from "dayjs";
import localizedFormat from "dayjs/plugin/localizedFormat";
import * as R from "ramda";

dayjs.extend(localizedFormat);

/**
 * Unsaved changes kept in this browser, so a crash, a reload or an
 * expired session does not lose them. Only the changed fields are kept,
 * each with the value it started from, so recovery can tell which fields
 * someone else saved in the meantime.
 *
 * The UI calls them "unsaved changes", never drafts: Draft is a
 * publishing state.
 */
export interface KeptChanges {
  version: 1;
  // When the changes were last kept (epoch ms).
  keptAt: number;
  // The object's name when the changes were kept.
  name?: string;
  fields: Record<string, { value: unknown; base: unknown }>;
}

export const RECOVERY_PREFIX = "cs:recovery:";

// Kept changes older than this are dropped (the RECOVERY_MAX_AGE setting).
export const DEFAULT_MAX_AGE_DAYS = 7;

export function recoveryKey({
  tenant,
  user,
  model,
  id,
}: {
  tenant?: string | null;
  user: string;
  model: string;
  id?: string | null;
}) {
  return `${RECOVERY_PREFIX}${tenant ?? "-"}:${user}:${model}:${id ?? "new"}`;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readKept(key: string): KeptChanges | null {
  try {
    const raw = storage()?.getItem(key);
    if (!raw) {
      return null;
    }
    const kept = JSON.parse(raw) as KeptChanges;

    return kept?.version === 1 && R.is(Object, kept.fields) ? kept : null;
  } catch {
    return null;
  }
}

/** Keeps the changes; false when the browser refused (blocked, full). */
export function writeKept(key: string, kept: KeptChanges): boolean {
  try {
    const store = storage();
    if (!store) {
      return false;
    }
    store.setItem(key, JSON.stringify(kept));
    return true;
  } catch {
    return false;
  }
}

export function removeKept(key: string) {
  try {
    storage()?.removeItem(key);
  } catch {
    // Nothing to remove.
  }
}

function keptKeys(): string[] {
  const store = storage();
  const keys: string[] = [];

  try {
    for (let index = 0; store && index < store.length; index++) {
      const key = store.key(index);
      if (key?.startsWith(RECOVERY_PREFIX)) {
        keys.push(key);
      }
    }
  } catch {
    // Storage went away; nothing to list.
  }
  return keys;
}

/** Drops kept changes older than maxAgeDays (and unreadable ones). */
export function pruneKept(maxAgeDays = DEFAULT_MAX_AGE_DAYS, now = Date.now()) {
  const oldest = now - maxAgeDays * 24 * 60 * 60 * 1000;

  for (const key of keptKeys()) {
    const kept = readKept(key);
    if (!kept || kept.keptAt < oldest) {
      removeKept(key);
    }
  }
}

/** Drops every kept change in this browser (on logout). */
export function clearKept() {
  for (const key of keptKeys()) {
    removeKept(key);
  }
}

export interface Recovery {
  // Fields whose value nobody changed since: the kept value is restored.
  clean: string[];
  // Fields saved by someone else since that differ from the kept value.
  clashes: string[];
  // Whether the object was saved with other values since (any field).
  changedSince: boolean;
}

/**
 * Three-way merge of kept changes with the object as it is now: a field
 * whose value is still its base takes the kept value; one that now holds
 * the kept value needs nothing; any other is a clash.
 */
export function mergeKept(
  kept: KeptChanges,
  current: Record<string, unknown>,
): Recovery {
  const clean: string[] = [];
  const clashes: string[] = [];
  let changedSince = false;

  for (const [name, { value, base }] of Object.entries(kept.fields)) {
    const now = current[name];

    if (R.equals(now, base)) {
      clean.push(name);
    } else {
      changedSince = true;
      if (!R.equals(now, value)) {
        clashes.push(name);
      }
    }
  }
  return { clean, clashes, changedSince };
}

/** When changes were kept: "14:02" today, "Nov 20, 2026 2:02 PM" before. */
export function formatKeptAt(keptAt: number, now = Date.now()) {
  const at = dayjs(keptAt);
  return at.isSame(dayjs(now), "day") ? at.format("LT") : at.format("lll");
}
