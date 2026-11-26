import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DistinctValuesFilter } from "@/components/filters/distinct-values-filter";
import { FilterRenderer } from "@/components/filters/renderer";
import type { FilterValues } from "@/components/filters/types";
import { joinFilterValues, splitFilterValues } from "@/lib/list-filters";
import { FieldType, type Model, type ModelField } from "@/types";

const httpGetMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({ get: httpGetMock }),
}));

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: { widgets: {} } }),
}));

const FIELD = {
  type: FieldType.CharField,
  verbose_name: "city",
} as unknown as ModelField;

const MODEL = { label: "calendar.project" } as Model;

function ControlledFilter({
  onChange,
}: {
  onChange: (values: FilterValues) => void;
}) {
  const [values, setValues] = useState<FilterValues>({});

  return (
    <DistinctValuesFilter
      field={FIELD}
      name="city"
      model={MODEL}
      values={values}
      onChange={(changes) => {
        const next = { ...values, ...changes } as FilterValues;
        setValues(next);
        onChange(next);
      }}
    />
  );
}

function renderWithClient(node: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      {node}
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  httpGetMock.mockReset();
  httpGetMock.mockImplementation(
    async (_url: string, { params }: { params: { search?: string } }) => ({
      data: params.search
        ? { values: ["Utrecht"], more: false }
        : { values: ["Amsterdam", "Den Haag, NL", "Utrecht"], more: true },
    }),
  );
});

describe("DistinctValuesFilter", () => {
  it("picks values from the table, a comma in a value escaped", async () => {
    const onChange = vi.fn();
    renderWithClient(<ControlledFilter onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /city/i }));
    await userEvent.click(await screen.findByText("Amsterdam"));
    await userEvent.click(screen.getByText("Den Haag, NL"));

    expect(httpGetMock).toHaveBeenCalledWith(
      "/content/calendar.project/filters/city/values",
      { params: { search: undefined } },
    );
    expect(onChange).toHaveBeenLastCalledWith({
      "": "Amsterdam,Den Haag\\, NL",
    });
    expect(
      screen.getByText("list_view.filters.more_values"),
    ).toBeInTheDocument();
  });

  it("searches the server for other values", async () => {
    renderWithClient(<ControlledFilter onChange={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /city/i }));
    await userEvent.type(screen.getByPlaceholderText(/search/i), "utr");

    await waitFor(() =>
      expect(httpGetMock).toHaveBeenLastCalledWith(
        "/content/calendar.project/filters/city/values",
        { params: { search: "utr" } },
      ),
    );
    await waitFor(() =>
      expect(screen.queryByText("Amsterdam")).not.toBeInTheDocument(),
    );
  });

  it("is the control the renderer shows for text without choices", () => {
    renderWithClient(
      <FilterRenderer
        field={FIELD}
        control="distinct"
        name="city"
        model={MODEL}
        values={{ "": "Amsterdam" }}
        onValueChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /city/i })).toHaveTextContent(
      "Amsterdam",
    );
  });
});

describe("filter values", () => {
  it("round-trips values with commas", () => {
    const values = ["a,b", "c", "d,,e"];

    expect(splitFilterValues(joinFilterValues(values))).toEqual(values);
    expect(splitFilterValues("1,2")).toEqual(["1", "2"]);
    expect(splitFilterValues("")).toEqual([]);
  });
});
