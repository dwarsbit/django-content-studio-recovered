import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { BooleanFilter } from "@/components/filters/boolean-filter";
import { DateRangeFilter } from "@/components/filters/date-range-filter";
import { MultiSelectFilter } from "@/components/filters/multi-select-filter";
import type {
  FilterComponentProps,
  FilterValues,
} from "@/components/filters/types";
import { FieldType, type Model, type ModelField } from "@/types";

function Controlled({
  Filter,
  field,
  initial,
  onChange,
}: {
  Filter: (props: FilterComponentProps) => React.ReactNode;
  field: ModelField;
  initial: FilterValues;
  onChange: (values: FilterValues) => void;
}) {
  const [values, setValues] = useState<FilterValues>(initial);

  return (
    <Filter
      field={field}
      name="status"
      model={{} as Model}
      values={values}
      onChange={(changes) => {
        const next = { ...values, ...changes } as FilterValues;
        setValues(next);
        onChange(next);
      }}
    />
  );
}

const cases: [
  string,
  FilterComponentProps["field"],
  FilterValues,
  typeof BooleanFilter,
][] = [
  [
    "a dropdown menu filter",
    {
      type: FieldType.CharField,
      verbose_name: "status",
      choices: [
        ["concept", "Concept"],
        ["published", "Published"],
      ],
    } as unknown as ModelField,
    { "": "concept" },
    MultiSelectFilter,
  ],
  [
    "a boolean filter",
    {
      type: FieldType.BooleanField,
      verbose_name: "status",
    } as unknown as ModelField,
    { "": "true" },
    BooleanFilter,
  ],
  [
    "a popover filter",
    {
      type: FieldType.DateField,
      verbose_name: "status",
    } as unknown as ModelField,
    { gte: "2026-01-01", lte: "2026-01-31" },
    DateRangeFilter,
  ],
];

describe("FilterTrigger clear button", () => {
  it.each(cases)(
    "clears %s without opening it",
    async (_, field, initial, Filter) => {
      const onChange = vi.fn();
      render(
        <Controlled
          Filter={Filter}
          field={field}
          initial={initial}
          onChange={onChange}
        />,
      );

      await userEvent.click(
        screen.getByRole("button", { name: "list_view.filters.clear" }),
      );

      expect(onChange).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.queryByRole("grid")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "list_view.filters.clear" }),
      ).not.toBeInTheDocument();
    },
  );

  it("clears with the keyboard without opening the filter", async () => {
    const onChange = vi.fn();
    render(
      <Controlled
        Filter={MultiSelectFilter}
        field={cases[0][1]}
        initial={cases[0][2]}
        onChange={onChange}
      />,
    );

    screen.getByRole("button", { name: "list_view.filters.clear" }).focus();
    await userEvent.keyboard("{Enter}");

    expect(onChange).toHaveBeenCalledWith({ "": null });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
