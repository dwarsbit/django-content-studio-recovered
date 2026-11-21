import * as R from "ramda";
import { useCallback, useEffect, useRef, useState } from "react";
import type { UseFormReturn } from "react-hook-form";

import { useAdminInfo } from "@/hooks/use-admin-info";
import { useMe } from "@/hooks/use-me";
import {
  DEFAULT_MAX_AGE_DAYS,
  type KeptChanges,
  mergeKept,
  pruneKept,
  readKept,
  type Recovery,
  recoveryKey,
  removeKept,
  sameValue,
  writeKept,
} from "@/lib/recovery";
import { useTenant } from "@/tenant";
import { FieldType, type Model, type Resource } from "@/types";

// How long after the last change the changes are kept.
const KEEP_DELAY = 2000;

// Files are uploaded on their own and never kept.
const FILE_TYPES = new Set<string>([FieldType.FileField, FieldType.ImageField]);

let pruned = false;

/** A write-only field's value: only whether it is set. */
function isSecret(value: unknown) {
  return R.is(Object, value) && "is_set" in (value as object);
}

export interface RecoveryOffer {
  kept: KeptChanges;
  recovery: Recovery;
  // After a restore that left clashes: they stay offered in Compare.
  restored?: string[];
}

/**
 * Keeps the editor's unsaved changes in this browser while they are
 * made, and offers changes kept earlier back when the object opens.
 */
export function useRecovery({
  form,
  model,
  id,
  enabled,
  ready,
}: {
  form: UseFormReturn<Partial<Resource>>;
  model: Model;
  id?: string | null;
  enabled: boolean;
  // The form holds the object's values (fetched, or the create form's).
  ready: boolean;
}) {
  const { data: me } = useMe();
  const { data: info } = useAdminInfo();
  const { tenantId } = useTenant();
  const key =
    enabled && me
      ? recoveryKey({
          tenant: tenantId,
          user: String(me.id),
          model: model.label,
          id,
        })
      : null;
  const [offer, setOfferState] = useState<RecoveryOffer | null>(null);
  // The offer as callbacks see it between renders.
  const offerRef = useRef<RecoveryOffer | null>(null);
  const setOffer = useCallback((next: RecoveryOffer | null) => {
    offerRef.current = next;
    setOfferState(next);
  }, []);
  // When the changes were last kept; null while nothing is (or the
  // browser refused).
  const [keptAt, setKeptAt] = useState<number | null>(null);
  // Whether what is kept under the key is this tab's: another tab with
  // the same object open must not drop it by having nothing to keep.
  const ownsRef = useRef(false);

  const keepable = useCallback(
    (name: string, value: unknown, base: unknown) => {
      const field = model.fields[name];
      const readonly =
        ((form.getValues() as Record<string, unknown>).__readonly_fields__ as
          string[] | undefined) ?? [];

      return (
        !!field &&
        !field.readonly &&
        !readonly.includes(name) &&
        !FILE_TYPES.has(field.type) &&
        !(model.admin.edit.recover_changes_exclude ?? []).includes(name) &&
        !isSecret(value) &&
        !isSecret(base)
      );
    },
    [form, model],
  );

  // Changes older than RECOVERY_MAX_AGE are dropped, once per page load.
  useEffect(() => {
    if (pruned || !info) {
      return;
    }
    pruned = true;
    const maxAge = info.settings.recovery_max_age;
    pruneKept(
      typeof maxAge === "number" && maxAge > 0 ? maxAge : DEFAULT_MAX_AGE_DAYS,
    );
  }, [info]);

  // Offer changes kept earlier, once the form holds the object.
  useEffect(() => {
    if (!key || !ready) {
      return;
    }

    const kept = readKept(key);
    if (!kept) {
      return;
    }

    const fields = R.pickBy(
      (field, name) => keepable(name, field.value, field.base),
      kept.fields,
    ) as KeptChanges["fields"];
    const usable = { ...kept, fields };
    const recovery = mergeKept(usable, form.getValues());

    if (R.isEmpty(recovery.clean) && R.isEmpty(recovery.clashes)) {
      removeKept(key);
      return;
    }
    // Kept changes live outside React (in localStorage); they are read
    // once the form holds the object.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncs from browser storage
    setOffer({ kept: usable, recovery });
    ownsRef.current = true;
  }, [key, ready, form, keepable, setOffer]);

  const keepNow = useCallback(() => {
    if (!key) {
      return;
    }

    const values = form.getValues() as Record<string, unknown>;
    const defaults = (form.formState.defaultValues ?? {}) as Record<
      string,
      unknown
    >;
    const fields: KeptChanges["fields"] = {};

    for (const name of Object.keys(model.fields)) {
      const value = values[name];
      const base = defaults[name];

      if (!sameValue(value, base) && keepable(name, value, base)) {
        // undefined does not survive JSON: an empty start is null.
        fields[name] = { value: value ?? null, base: base ?? null };
      }
    }

    // Changes still on offer stay kept until restored or discarded.
    const pending = offerRef.current;
    const all = pending
      ? {
          ...R.pick(
            [...pending.recovery.clean, ...pending.recovery.clashes].filter(
              (name) => !pending.restored?.includes(name),
            ),
            pending.kept.fields,
          ),
          ...fields,
        }
      : fields;

    if (R.isEmpty(all)) {
      if (ownsRef.current) {
        removeKept(key);
        ownsRef.current = false;
      }
      setKeptAt(null);
      return;
    }

    const now = Date.now();
    const ok = writeKept(key, {
      version: 1,
      keptAt: pending && R.isEmpty(fields) ? pending.kept.keptAt : now,
      name: (values.__str__ as string | undefined) ?? undefined,
      fields: all,
    });
    ownsRef.current = ok;
    setKeptAt(ok && !R.isEmpty(fields) ? now : null);
  }, [key, form, model, keepable]);

  // Keep changes a moment after the last one, and right away when the
  // tab is hidden or closed.
  useEffect(() => {
    if (!key || !ready) {
      return;
    }

    // Changes made before the object finished loading count too.
    let timer: ReturnType<typeof setTimeout> | undefined = setTimeout(
      keepNow,
      KEEP_DELAY,
    );
    const subscription = form.watch(() => {
      clearTimeout(timer);
      timer = setTimeout(keepNow, KEEP_DELAY);
    });
    const flush = () => {
      clearTimeout(timer);
      keepNow();
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        flush();
      }
    };
    // Another tab kept changes to the same object: they are its own
    // until this tab changes something again (the last change wins).
    const onStorage = (event: StorageEvent) => {
      if (event.key === key) {
        ownsRef.current = false;
      }
    };

    window.addEventListener("pagehide", flush);
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      clearTimeout(timer);
      subscription.unsubscribe();
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [key, ready, form, keepNow]);

  /** Puts kept values in the form as unsaved changes. */
  const restore = useCallback(
    (names: string[]) => {
      const current = offerRef.current;
      if (!current) {
        return;
      }

      for (const name of names) {
        form.setValue(name as never, current.kept.fields[name].value as never, {
          shouldDirty: true,
          shouldValidate: true,
        });
      }

      const restored = [...(current.restored ?? []), ...names];
      const left = current.recovery.clashes.filter(
        (name) => !restored.includes(name),
      );
      setOffer(left.length ? { ...current, restored } : null);
      keepNow();
    },
    [form, keepNow, setOffer],
  );

  /** Forgets the kept changes on offer. */
  const discard = useCallback(() => {
    setOffer(null);
    keepNow();
  }, [keepNow, setOffer]);

  /** After a save: nothing is unsaved any more. */
  const clear = useCallback(() => {
    setOffer(null);
    setKeptAt(null);
    ownsRef.current = false;
    if (key) {
      removeKept(key);
    }
  }, [key, setOffer]);

  return { offer, keptAt, restore, discard, clear };
}
