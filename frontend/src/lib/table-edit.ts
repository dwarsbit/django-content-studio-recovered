import { FieldType, FieldWidget, type ModelField } from "@/types";

export type CellKind =
  "boolean" | "choice" | "relation" | "date" | "datetime" | "text";

/** How a table cell edits a field. */
export function getCellKind(field: ModelField | undefined): CellKind {
  if (!field) {
    return "text";
  }

  if (field.type === FieldType.BooleanField) {
    return "boolean";
  }

  if (field.choices?.length) {
    return "choice";
  }

  if (
    field.widget_class === FieldWidget.ForeignKeyWidget ||
    (field.type as string) === "ForeignKey" ||
    (field.type as string) === "OneToOneField"
  ) {
    return "relation";
  }

  if (field.type === FieldType.DateField) {
    return "date";
  }

  if (field.type === FieldType.DateTimeField) {
    return "datetime";
  }

  return "text";
}
