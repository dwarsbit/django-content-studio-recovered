import * as R from "ramda";

import type { FormField, Model, ModelField } from "@/types";

export type ActionValues = Record<string, unknown>;

/**
 * The model an action's dialog renders its fields with: the model's
 * own fields for model field inputs, and the description a form field
 * input carries. Duplicate checks belong to saving an object, not to
 * an action, so they are left out.
 */
export function getDialogModel(model: Model, fields: FormField[]): Model {
  return {
    ...model,
    unique_sets: [],
    fields: Object.fromEntries(
      fields.map((field) => [
        field.name,
        R.omit(["unique"], field.input ?? model.fields[field.name] ?? {}),
      ]),
    ) as Record<string, ModelField>,
  };
}

/**
 * The values a dialog starts with: the given values (a button's object)
 * for the fields they hold, otherwise the field's default.
 */
export function getInitialValues(
  model: Model,
  fields: FormField[],
  values?: ActionValues,
): ActionValues {
  return Object.fromEntries(
    fields.map((field) => {
      const modelField = field.input ?? model.fields[field.name];
      const value =
        values && field.name in values
          ? values[field.name]
          : modelField?.default;

      return [field.name, value ?? null];
    }),
  );
}
