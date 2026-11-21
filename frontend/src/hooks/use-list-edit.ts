import { useQueryClient } from "@tanstack/react-query";
import * as R from "ramda";
import { useCallback, useState } from "react";

import { useHttp } from "@/hooks/use-http";
import type { Model } from "@/types";

type Row = { id: string; [p: string]: unknown };

// Pending edits: row id -> data key (a translated column, or the field
// name) -> value. Base values are the row's values when the edit began.
export type PendingEdits = Record<string, Record<string, unknown>>;
export type EditErrors = Record<string, Record<string, string[]>>;

export interface ListEdit {
  editable: string[];
  pending: PendingEdits;
  errors: EditErrors;
  count: number;
  rowCount: number;
  isSaving: boolean;
  set(row: Row, key: string, value: unknown): void;
  discard(): void;
  save(): Promise<{ saved: number; failed: number }>;
}

const sameValue = (a: unknown, b: unknown) => {
  const id = (v: unknown) =>
    v && typeof v === "object" && "id" in v ? String((v as Row).id) : v;

  return R.equals(id(a), id(b));
};

export function useListEdit(model: Model | undefined, rows: Row[]): ListEdit {
  const http = useHttp();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingEdits>({});
  const [errors, setErrors] = useState<EditErrors>({});
  const [isSaving, setSaving] = useState(false);
  const editable = model?.admin.list.edit ?? [];

  const set = useCallback((row: Row, key: string, value: unknown) => {
    setPending((previous) => {
      const values = { ...(previous[row.id] ?? {}) };

      if (sameValue(row[key], value)) {
        delete values[key];
      } else {
        values[key] = value;
      }

      const next = { ...previous, [row.id]: values };

      if (R.isEmpty(values)) {
        delete next[row.id];
      }

      return next;
    });
    setErrors((previous) => {
      if (!previous[row.id]?.[key]) {
        return previous;
      }

      const rowErrors = R.omit([key], previous[row.id]);

      return R.isEmpty(rowErrors)
        ? R.omit([row.id], previous)
        : { ...previous, [row.id]: rowErrors };
    });
  }, []);

  const discard = useCallback(() => {
    setPending({});
    setErrors({});
  }, []);

  const save = async () => {
    if (!model) {
      return { saved: 0, failed: 0 };
    }

    setSaving(true);

    try {
      const body = Object.entries(pending).map(([id, values]) => {
        const row = rows.find((r) => String(r.id) === id);

        return {
          id,
          values,
          base: Object.fromEntries(
            Object.keys(values).map((key) => [key, row?.[key]]),
          ),
        };
      });
      const { data } = await http.post<{
        saved: string[];
        errors: EditErrors;
      }>(`/content/${model.label}/list-edit`, { rows: body });
      const savedIds = new Set(data.saved.map(String));

      setPending((previous) =>
        R.pickBy((_, id) => !savedIds.has(String(id)), previous),
      );
      setErrors(data.errors);
      await queryClient.invalidateQueries({
        queryKey: ["resources", model.label],
      });

      return {
        saved: savedIds.size,
        failed: Object.keys(data.errors).length,
      };
    } finally {
      setSaving(false);
    }
  };

  return {
    editable,
    pending,
    errors,
    count: Object.values(pending).reduce(
      (total, values) => total + Object.keys(values).length,
      0,
    ),
    rowCount: Object.keys(pending).length,
    isSaving,
    set,
    discard,
    save,
  };
}
