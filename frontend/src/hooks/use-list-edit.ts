import { useQueryClient } from "@tanstack/react-query";
import * as R from "ramda";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useHttp } from "@/hooks/use-http";
import type { Model } from "@/types";

type Row = { id: string; __str__?: string; [p: string]: unknown };

// Values shown in place of the row's own while they save or after a
// failed save: row id -> data key (a translated column, or the field
// name) -> value.
export type PendingEdits = Record<string, Record<string, unknown>>;
export type EditErrors = Record<string, Record<string, string[]>>;

export interface ListEdit {
  editable: string[];
  pending: PendingEdits;
  errors: EditErrors;
  saving: Set<string>;
  saved: Set<string>;
  set(row: Row, key: string, value: unknown): void;
  revert(id: string, key: string): void;
}

const cellKey = (id: string, key: string) => `${id}:${key}`;

const sameValue = (a: unknown, b: unknown) => {
  const id = (v: unknown) =>
    v && typeof v === "object" && "id" in v ? String((v as Row).id) : v;

  return R.equals(id(a), id(b));
};

/**
 * In-place editing of the table (WIP prototype of list_edit): a cell
 * saves as soon as it is left, through the list-edit endpoint with the
 * value it started from (a conflict check), and offers Undo in a toast.
 */
export function useListEdit(model: Model | undefined): ListEdit {
  const { t } = useTranslation();
  const http = useHttp();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingEdits>({});
  const [errors, setErrors] = useState<EditErrors>({});
  const [saving, setSaving] = useState<Set<string>>(() => new Set());
  const [saved, setSaved] = useState<Set<string>>(() => new Set());
  const timers = useRef<Record<string, number>>({});
  const editable = model?.admin.list.edit ?? [];

  const clearCell = useCallback((id: string, key: string) => {
    setPending((previous) => dropKey(previous, id, key));
    setErrors((previous) => dropKey(previous, id, key));
  }, []);

  const save = async (row: Row, key: string, value: unknown, base: unknown) => {
    if (!model) {
      return false;
    }

    const cell = cellKey(row.id, key);

    setPending((previous) => ({
      ...previous,
      [row.id]: { ...(previous[row.id] ?? {}), [key]: value },
    }));
    setErrors((previous) => dropKey(previous, row.id, key));
    setSaving((previous) => new Set(previous).add(cell));

    try {
      const { data } = await http.post<{
        saved: string[];
        errors: EditErrors;
      }>(`/content/${model.label}/list-edit`, {
        rows: [{ id: row.id, values: { [key]: value }, base: { [key]: base } }],
      });
      const rowErrors = data.errors[row.id];

      if (rowErrors) {
        setErrors((previous) => ({
          ...previous,
          [row.id]: {
            ...(previous[row.id] ?? {}),
            [key]: rowErrors[key] ?? Object.values(rowErrors).flat(),
          },
        }));
        return false;
      }

      // The list shows the saved value at once; the refetch confirms it.
      queryClient.setQueriesData<{ results: Row[] }>(
        { queryKey: ["resources", model.label] },
        (old) =>
          old && {
            ...old,
            results: old.results.map((r) =>
              String(r.id) === String(row.id) ? { ...r, [key]: value } : r,
            ),
          },
      );
      setPending((previous) => dropKey(previous, row.id, key));
      setSaved((previous) => new Set(previous).add(cell));
      window.clearTimeout(timers.current[cell]);
      timers.current[cell] = window.setTimeout(
        () =>
          setSaved((previous) => {
            const next = new Set(previous);
            next.delete(cell);
            return next;
          }),
        1600,
      );
      void queryClient.invalidateQueries({
        queryKey: ["resources", model.label],
      });

      return true;
    } finally {
      setSaving((previous) => {
        const next = new Set(previous);
        next.delete(cell);
        return next;
      });
    }
  };

  const set = (row: Row, key: string, value: unknown) => {
    const original = row[key];

    if (sameValue(original, value)) {
      clearCell(row.id, key);
      return;
    }

    void save(row, key, value, original).then((ok) => {
      if (!ok || !model) {
        return;
      }

      const name = key.replace(/_[a-z]{2}(_[a-z]+)?$/i, "");
      const label =
        model.fields[key]?.verbose_name ??
        model.fields[name]?.verbose_name ??
        key;

      toast.success(
        t("list_edit.saved_cell", {
          field: String(label).charAt(0).toUpperCase() + String(label).slice(1),
        }),
        {
          description: row.__str__,
          action: {
            label: t("list_edit.undo"),
            onClick: () =>
              void save({ ...row, [key]: value }, key, original, value),
          },
        },
      );
    });
  };

  return {
    editable,
    pending,
    errors,
    saving,
    saved,
    set,
    revert: clearCell,
  };
}

function dropKey<T>(
  record: Record<string, Record<string, T>>,
  id: string,
  key: string,
) {
  if (!record[id] || !(key in record[id])) {
    return record;
  }

  const values = R.omit([key], record[id]);

  return R.isEmpty(values) ? R.omit([id], record) : { ...record, [id]: values };
}
