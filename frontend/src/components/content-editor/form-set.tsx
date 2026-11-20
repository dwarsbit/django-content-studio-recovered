import * as R from "ramda";
import type React from "react";

import { useConditions } from "@/hooks/use-conditions";
import type {
  FormField as IFormField,
  FormLayout,
  FormSet,
  Model,
} from "@/types";

import { Conditional } from "./conditional";
import { useResetInvalidInput } from "./conditional-fields";
import { FormField } from "./form-field";

/**
 * For the card around a form set: hides the card while the form set
 * shows nothing, such as an activity log on the create form or fields
 * that are all hidden by their conditions.
 */
export const HIDE_EMPTY_FORM_SET =
  "[&:not(:has([data-slot=form-set-fields]>:not(:empty)))]:hidden";

export function FormSet({
  formSet,
  model,
  hiddenFields = [],
}: {
  formSet: FormSet;
  model: Model;
  hiddenFields?: string[];
}) {
  return (
    <div>
      {(formSet.title || formSet.description) && (
        <div className="px-5 py-3 border-b">
          {formSet.title && (
            <h4 className="font-semibold first-letter:uppercase">
              {formSet.title}
            </h4>
          )}
          {formSet.description ? (
            <div className="text-xs text-muted-foreground">
              {formSet.description}
            </div>
          ) : null}
        </div>
      )}
      {/* A container, so a row of fields stacks when the card is narrow. */}
      <div className="@container p-5 space-y-5" data-slot="form-set-fields">
        {formSet.fields.map((formField, idx) =>
          R.has("fields", formField) ? (
            <LayoutRow
              key={idx}
              layout={formField}
              model={model}
              hiddenFields={hiddenFields}
            />
          ) : (
            !hiddenFields.includes(formField.name) && (
              <Conditional
                key={idx}
                when={formField.when}
                fields={formField.type === "field" ? [formField.name] : []}
              >
                <FormField formField={formField} model={model} />
              </Conditional>
            )
          ),
        )}
      </div>
    </div>
  );
}

/**
 * A FieldLayout row: its fields side by side. A field hidden by its
 * condition gives its column to the others; a row without shown fields
 * is left out.
 */
function LayoutRow({
  layout,
  model,
  hiddenFields,
}: {
  layout: FormLayout;
  model: Model;
  hiddenFields: string[];
}) {
  const fields = layout.fields.filter((f) => !hiddenFields.includes(f.name));
  const shown = useConditions(fields.map((f) => f.when));
  const visible = fields.filter((_, idx) => shown[idx]);

  useResetInvalidInput(
    fields
      .filter((f, idx) => !shown[idx] && f.type === "field")
      .map((f) => f.name),
  );

  return (
    visible.length > 0 && (
      <div
        // Side by side where the card has room, stacked where it has not
        // (a phone, the sidebar). minmax(0, 1fr) keeps the columns equal
        // when a field holds unbreakable content, such as a long file
        // name.
        className="grid gap-4 grid-cols-1 @sm:[grid-template-columns:repeat(var(--columns),minmax(0,1fr))]"
        style={{ "--columns": visible.length } as React.CSSProperties}
      >
        {visible.map((innerFormField: IFormField) => (
          <FormField
            key={innerFormField.name}
            formField={innerFormField}
            model={model}
          />
        ))}
      </div>
    )
  );
}
