import React, { useContext } from "react";
import { useFormContext, useWatch } from "react-hook-form";

import { ActivityLog } from "@/components/form-components/activity-log";
import { Analytics } from "@/components/form-components/analytics";
import { ComponentButton } from "@/components/form-components/button";
import { Callout } from "@/components/form-components/callout";
import { Link } from "@/components/form-components/link";
import { LinkButton } from "@/components/form-components/link-button";
import { SEOPreview } from "@/components/form-components/seo-preview";
import { Subtitle } from "@/components/form-components/subtitle";
import { Text } from "@/components/form-components/text";
import { Title } from "@/components/form-components/title";
import { FormatRenderer } from "@/components/formats/renderer";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormDescription,
  FormField as RootFormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Switch } from "@/components/ui/switch";
import { PermissionMatrixWidget } from "@/components/widgets/permission-matrix-widget";
import { WidgetRenderer } from "@/components/widgets/renderer";
import { useAdminInfo } from "@/hooks/use-admin-info";
import { cn } from "@/lib/utils";
import { FieldWidget, type FormField as IFormField, type Model } from "@/types";

import {
  SharedFieldMarker,
  TranslationReference,
  useContentLanguage,
  useTranslatedName,
} from "./content-language";
import { EditorReadOnlyContext } from "./editor-read-only";
import { UniqueSetWarning, UniqueWarning } from "./unique-warning";

const COMPONENTS: Partial<
  Record<
    IFormField["component_type"],
    React.ComponentType<{
      model: Model;
      formField: IFormField;
    }>
  >
> = {
  Link,
  LinkButton,
  Button: ComponentButton,
  ActivityLog,
  Analytics,
  Title,
  Subtitle,
  Text,
  Callout,
  SEOPreview,
};

export function FormField({
  formField,
  model,
}: {
  formField: IFormField;
  model: Model;
}) {
  const form = useFormContext();
  const { data: info } = useAdminInfo();
  const translation = useTranslatedName(formField.name);
  const { language } = useContentLanguage();
  const modelField = model.fields[formField.name];
  const label = formField.label || modelField?.verbose_name;
  // The studio's read-only fields travel with the form values: the
  // create form starts from the studio's list, a saved object brings
  // its own.
  const readonlyFields = useWatch({ name: "__readonly_fields__" }) as
    string[] | undefined;
  const editorReadOnly = useContext(EditorReadOnlyContext);
  const isReadonly =
    editorReadOnly ||
    !modelField ||
    modelField.readonly ||
    formField.readonly ||
    (readonlyFields?.includes(formField.name) ?? false);

  // Checkboxes render their label inline after the box, not above it.
  const widgetClass =
    formField.widget?.name ??
    modelField?.widget_class ??
    info?.widgets[modelField?.type ?? ""]?.name;
  const isCheckbox =
    modelField !== undefined && widgetClass === FieldWidget.CheckboxWidget;
  const isSwitch =
    modelField !== undefined && widgetClass === FieldWidget.SwitchWidget;
  // The label toggles checkbox- and switch-based controls through its
  // htmlFor association, so it reads as clickable.
  const labelToggles =
    !isReadonly &&
    (widgetClass === FieldWidget.CheckboxWidget ||
      widgetClass === FieldWidget.SwitchWidget);

  // A component that renders nothing (an activity log on the create
  // form, a callout without text) takes no room in its form set.
  if (formField.type !== "field") {
    return (
      <div className="empty:hidden">
        <ComponentRenderer formField={formField} model={model} />
      </div>
    );
  }

  return (
    <div>
      <RootFormField
        key={translation.name}
        control={form.control}
        name={translation.name}
        render={({ field }) => {
          // The label's text, capitalized; a required field gets a mark
          // through CSS so the label's text stays the field's name.
          const labelText = (
            <span
              className={cn(
                "first-letter:uppercase",
                !isReadonly &&
                  !labelToggles &&
                  modelField?.required &&
                  "after:content-['_*'] after:text-muted-foreground after:font-normal",
              )}
            >
              {label}
              {translation.translated &&
                translation.name !== formField.name && (
                  <span className="ml-1.5 rounded bg-muted px-1 py-px text-[10px] font-semibold uppercase tracking-wide text-muted-foreground align-middle">
                    {language}
                  </span>
                )}
              {translation.shared && <SharedFieldMarker />}
            </span>
          );
          const control =
            isReadonly &&
            modelField &&
            widgetClass === FieldWidget.PermissionMatrixWidget ? (
              // Read-only permissions stay a matrix, which reads better
              // than a list of every permission's name.
              <PermissionMatrixWidget
                readOnly
                model={model}
                name={formField.name}
                value={field.value}
                onChange={field.onChange}
              />
            ) : isReadonly && (isCheckbox || isSwitch) ? (
              // A read-only box or switch keeps its shape, so it reads like
              // its editable neighbours, but cannot be toggled.
              <FormControl>
                {isCheckbox ? (
                  <Checkbox
                    checked={field.value === true}
                    disabled
                    aria-readonly
                  />
                ) : (
                  <Switch
                    checked={field.value === true}
                    disabled
                    aria-readonly
                  />
                )}
              </FormControl>
            ) : isReadonly ? (
              <div className="min-h-9 flex items-center px-3 rounded-md border border-dashed bg-muted/40 text-muted-foreground cursor-default">
                <FormatRenderer
                  value={field.value}
                  field={modelField}
                  display="field"
                />
              </div>
            ) : (
              <FormControl>
                <WidgetRenderer
                  model={model}
                  {...field}
                  widget={formField.widget}
                />
              </FormControl>
            );

          return (
            <FormItem className={isCheckbox ? "gap-1" : undefined}>
              {isCheckbox ? (
                // The box, then the label with the help text under it.
                <div className="flex items-start gap-2.5 [&>[role=checkbox]]:mt-0.5">
                  {control}
                  <div className="min-w-0">
                    <FormLabel
                      className={cn(
                        "text-foreground",
                        isReadonly ? "cursor-default" : "cursor-pointer",
                      )}
                    >
                      {labelText}
                    </FormLabel>
                    {modelField?.help_text && (
                      <FormDescription className="mt-0.5 text-xs">
                        {modelField.help_text}
                      </FormDescription>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  <FormLabel
                    className={cn(
                      "text-foreground",
                      labelToggles && "cursor-pointer",
                    )}
                  >
                    {labelText}
                  </FormLabel>
                  {control}
                  {translation.translated && !isReadonly && (
                    <TranslationReference
                      name={formField.name}
                      column={translation.name}
                    />
                  )}
                </>
              )}
              {!isReadonly && modelField?.unique && (
                <UniqueWarning model={model} name={formField.name} />
              )}
              {!isReadonly &&
                model.unique_sets
                  ?.filter((uniqueSet) =>
                    uniqueSet.fields.includes(formField.name),
                  )
                  .map((uniqueSet) => (
                    <UniqueSetWarning
                      key={uniqueSet.id}
                      model={model}
                      uniqueSet={uniqueSet}
                      name={formField.name}
                    />
                  ))}
              {!isCheckbox && modelField?.help_text && (
                <FormDescription className="text-xs">
                  {modelField.help_text}
                </FormDescription>
              )}
              <FormMessage />
            </FormItem>
          );
        }}
      />
    </div>
  );
}

/**
 * Renders a component (Link, LinkButton, Button, ActivityLog, Title,
 * Subtitle, Text, Callout, SEOPreview) of the edit page, in a form set
 * or in the header.
 */
export function ComponentRenderer({
  formField,
  model,
}: {
  formField: IFormField;
  model: Model;
}) {
  const Component = COMPONENTS[formField.component_type];

  return Component
    ? React.createElement(Component, { formField, model })
    : null;
}
