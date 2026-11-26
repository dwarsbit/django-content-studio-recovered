import { type ComponentType, useMemo } from "react";

import { useAdminInfo } from "@/hooks/use-admin-info";
import {
  FieldType,
  FieldWidget,
  type FilterControl,
  type Model,
  type ModelField,
} from "@/types";

import { BooleanFilter } from "./boolean-filter";
import { DateRangeFilter } from "./date-range-filter";
import { DistinctValuesFilter } from "./distinct-values-filter";
import { ForeignKeyFilter } from "./foreign-key-filter";
import { ManyToManyFilter } from "./many-to-many-filter";
import { MultiSelectFilter } from "./multi-select-filter";
import { NumberFilter } from "./number-filter";
import type {
  FilterChanges,
  FilterComponentProps,
  FilterValues,
} from "./types";

type FilterComponent = ComponentType<FilterComponentProps>;

const NUMBER_TYPES: string[] = [
  FieldType.IntegerField,
  FieldType.DecimalField,
  FieldType.FloatField,
];

// Every integer field (PositiveIntegerField, BigIntegerField, ...)
// filters on a number range.
function isNumberType(type: string) {
  return NUMBER_TYPES.includes(type) || type.endsWith("IntegerField");
}

const CONTROLS: Record<FilterControl, FilterComponent> = {
  choices: MultiSelectFilter,
  boolean: BooleanFilter,
  date: DateRangeFilter,
  number: NumberFilter,
  relation: ForeignKeyFilter,
  many: ManyToManyFilter,
  distinct: DistinctValuesFilter,
};

export function FilterRenderer({
  field,
  control,
  name,
  model,
  values,
  onValueChange,
  defaultOpen,
}: {
  field: ModelField;
  // The control the server picked for the field (get_filter_control);
  // without it the field's type and widget decide.
  control?: FilterControl;
  name: string;
  model: Model;
  values: FilterValues;
  onValueChange(changes: FilterChanges): void;
  defaultOpen?: boolean;
}) {
  const { data: info } = useAdminInfo();
  const widgetClass = field.widget_class ?? info?.widgets[field.type]?.name;

  const FilterComp = useMemo<FilterComponent | null>(() => {
    if (control) {
      return CONTROLS[control] ?? null;
    }
    if (widgetClass === FieldWidget.InputWidget && field.choices) {
      return MultiSelectFilter;
    }
    if (widgetClass === FieldWidget.MultiSelectWidget) {
      return MultiSelectFilter;
    }
    if (field.type === FieldType.BooleanField) {
      return BooleanFilter;
    }
    if (
      field.type === FieldType.DateField ||
      field.type === FieldType.DateTimeField
    ) {
      return DateRangeFilter;
    }
    if (isNumberType(field.type)) {
      return NumberFilter;
    }
    if (widgetClass === FieldWidget.ForeignKeyWidget) {
      return ForeignKeyFilter;
    }
    if (
      widgetClass === FieldWidget.ManyToManyWidget ||
      widgetClass === FieldWidget.PermissionMatrixWidget
    ) {
      return ManyToManyFilter;
    }
    return null;
  }, [control, field, widgetClass]);

  return (
    FilterComp && (
      <FilterComp
        field={field}
        name={name}
        model={model}
        values={values}
        onChange={onValueChange}
        defaultOpen={defaultOpen}
      />
    )
  );
}
