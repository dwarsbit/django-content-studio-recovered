import { useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import * as R from "ramda";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useHttp } from "@/hooks/use-http";
import type { Model } from "@/types";

type Row = { id: string; __str__?: string; [p: string]: unknown };

// Per row id, per data key (a translated column, or the field name).
type PerCell<T> = Record<string, Record<string, T>>;

export interface TableEdit {
  // The columns this editor may edit in place (table_edit).
  editable: string[];
  // Values shown in place of the row's own: while a cell saves, and
  // after a failed save until it is retried or reverted.
  pending: PerCell<unknown>;
  errors: PerCell<string[]>;
  // "<row id>:<key>" of the cells saving now and of those just saved.
  saving: Set<string>;
  saved: Set<string>;
  // Saves a cell's new value; the same value clears a failed cell.
  set(row: Row, key: string, value: unknown): void;
  // Drops a failed cell's value: the row's own shows again.
  revert(id: string, key: string): void;
}

export const cellId = (id: string, key: string) => `${id}:${key}`;

// Related objects compare by id; everything else by value.
export function sameCellValue(a: unknown, b: unknown) {
  const comparable = (value: unknown) =>
    value && typeof value === "object" && "id" in value
      ? String((value as Row).id)
      : value;

  return R.equals(comparable(a), comparable(b));
}

// How long a saved cell shows its check.
const SAVED_MS = 1600;

/**
 * Inline editing of the table (table_edit): a cell saves as soon as the
 * editor leaves it, with the value the list showed as its base, so a
 * value someone else changed meanwhile is refused instead of
 * overwritten. A saved cell offers Undo in a toast; a failed one keeps
 * the typed value with the reason.
 */
export function useTableEdit(model: Model | undefined): TableEdit {
  const { t } = useTranslation();
  const http = useHttp();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PerCell<unknown>>({});
  const [errors, setErrors] = useState<PerCell<string[]>>({});
  const [saving, setSaving] = useState<Set<string>>(() => new Set());
  const [saved, setSaved] = useState<Set<string>>(() => new Set());
  const timers = useRef<Record<string, number>>({});
  const editable = model?.admin.list.edit ?? [];

  useEffect(() => {
    const current = timers.current;

    return () => Object.values(current).forEach(window.clearTimeout);
  }, []);

  // A save in flight would be lost with the page.
  useEffect(() => {
    if (saving.size === 0) {
      return;
    }

    const handler = (event: BeforeUnloadEvent) => event.preventDefault();

    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [saving.size]);

  const revert = useCallback((id: string, key: string) => {
    setPending((previous) => dropCell(previous, id, key));
    setErrors((previous) => dropCell(previous, id, key));
  }, []);

  const label = (key: string) => {
    const field =
      model?.fields[key] ??
      model?.fields[
        Object.entries(model?.admin.translations?.fields ?? {}).find(
          ([, columns]) => Object.values(columns).includes(key),
        )?.[0] ?? ""
      ];
    const name = String(field?.verbose_name ?? key);

    return name.charAt(0).toUpperCase() + name.slice(1);
  };

  const save = async (
    row: Row,
    key: string,
    value: unknown,
    base: unknown,
  ): Promise<boolean> => {
    if (!model) {
      return false;
    }

    const cell = cellId(row.id, key);
    const fail = (messages: string[]) =>
      setErrors((previous) => ({
        ...previous,
        [row.id]: { ...(previous[row.id] ?? {}), [key]: messages },
      }));

    setPending((previous) => ({
      ...previous,
      [row.id]: { ...(previous[row.id] ?? {}), [key]: value },
    }));
    setErrors((previous) => dropCell(previous, row.id, key));
    setSaving((previous) => new Set(previous).add(cell));

    try {
      const { data } = await http.post<{
        values: Record<string, unknown>;
      }>(`/content/${model.label}/${row.id}/table-edit`, {
        values: { [key]: value },
        base: { [key]: base },
      });
      const savedValue = key in data.values ? data.values[key] : value;

      // The list shows the saved value at once; the refetch confirms it
      // (and may move the row when the list is sorted or filtered by it).
      queryClient.setQueriesData<{ results: Row[] }>(
        { queryKey: ["resources", model.label] },
        (old) =>
          old?.results && {
            ...old,
            results: old.results.map((r) =>
              String(r.id) === String(row.id) ? { ...r, [key]: savedValue } : r,
            ),
          },
      );
      setPending((previous) => dropCell(previous, row.id, key));
      setSaved((previous) => new Set(previous).add(cell));
      window.clearTimeout(timers.current[cell]);
      timers.current[cell] = window.setTimeout(
        () =>
          setSaved((previous) => {
            const next = new Set(previous);
            next.delete(cell);
            return next;
          }),
        SAVED_MS,
      );
      void queryClient.invalidateQueries({
        queryKey: ["resources", model.label],
      });

      return true;
    } catch (error) {
      fail(getCellErrors(error, key, t("table_edit.failed")));

      // Someone else changed the value: the list shows theirs once the
      // editor reverts the cell.
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        void queryClient.invalidateQueries({
          queryKey: ["resources", model.label],
        });
      }
      return false;
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

    if (sameCellValue(original, value)) {
      revert(row.id, key);
      return;
    }

    void save(row, key, value, original).then((ok) => {
      if (!ok) {
        return;
      }

      toast.success(t("table_edit.saved", { field: label(key) }), {
        description: row.__str__,
        action: {
          label: t("table_edit.undo"),
          onClick: () =>
            void save({ ...row, [key]: value }, key, original, value),
        },
      });
    });
  };

  return { editable, pending, errors, saving, saved, set, revert };
}

/**
 * A failed save's messages for one cell: the cell's own field errors,
 * a conflict, the errors that belong to no field, or the fallback.
 */
export function getCellErrors(
  error: unknown,
  key: string,
  fallback: string,
): string[] {
  if (!axios.isAxiosError(error) || !error.response) {
    return [fallback];
  }

  const data = error.response.data as Record<string, unknown> | undefined;
  const source =
    error.response.status === 409
      ? (data?.conflicts as Record<string, unknown> | undefined)
      : data;
  const messages = [
    source?.[key],
    source?.non_field_errors,
    source?.detail,
  ].flatMap((entry) =>
    Array.isArray(entry)
      ? entry.map(String)
      : typeof entry === "string"
        ? [entry]
        : [],
  );

  return messages.length > 0 ? messages : [fallback];
}

function dropCell<T>(record: PerCell<T>, id: string, key: string) {
  if (!record[id] || !(key in record[id])) {
    return record;
  }

  const values = R.omit([key], record[id]);

  return R.isEmpty(values) ? R.omit([id], record) : { ...record, [id]: values };
}
