import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it, vi } from "vitest";

import { EditableCell } from "@/components/table-edit/editable-cell";
import { getCellErrors, sameCellValue } from "@/hooks/use-table-edit";
import { getCellKind } from "@/lib/table-edit";
import { FieldType, type Model, type ModelField } from "@/types";

const field = (props: Omit<Partial<ModelField>, "type"> & { type: unknown }) =>
  ({ verbose_name: "field", ...props }) as unknown as ModelField;

const MODEL = {
  label: "blog.article",
  fields: {
    title: field({ type: FieldType.CharField, verbose_name: "title" }),
    views: field({ type: FieldType.IntegerField, verbose_name: "views" }),
    featured: field({ type: FieldType.BooleanField, verbose_name: "featured" }),
  },
} as unknown as Model;

function responseError(status: number, data: unknown) {
  const headers = new AxiosHeaders();

  return new AxiosError("failed", "ERR", undefined, undefined, {
    status,
    data,
    statusText: "",
    headers,
    config: { headers },
  });
}

describe("getCellKind", () => {
  it("picks a cell per field", () => {
    expect(getCellKind(field({ type: FieldType.BooleanField }))).toBe(
      "boolean",
    );
    expect(
      getCellKind(field({ type: FieldType.CharField, choices: [["a", "A"]] })),
    ).toBe("choice");
    expect(getCellKind(field({ type: "ForeignKey" }))).toBe("relation");
    expect(getCellKind(field({ type: FieldType.DateField }))).toBe("date");
    expect(getCellKind(field({ type: FieldType.DateTimeField }))).toBe(
      "datetime",
    );
    expect(getCellKind(field({ type: FieldType.IntegerField }))).toBe("text");
    expect(getCellKind(undefined)).toBe("text");
  });
});

describe("sameCellValue", () => {
  it("compares related objects by id", () => {
    expect(sameCellValue({ id: 3, __str__: "Ann" }, { id: "3" })).toBe(true);
    expect(sameCellValue({ id: 3 }, { id: 4 })).toBe(false);
    expect(sameCellValue("a", "a")).toBe(true);
    expect(sameCellValue(null, "")).toBe(false);
  });
});

describe("getCellErrors", () => {
  it("reads the cell's own errors, then the general ones", () => {
    expect(
      getCellErrors(
        responseError(400, { title: ["This field may not be blank."] }),
        "title",
        "Failed",
      ),
    ).toEqual(["This field may not be blank."]);
    expect(
      getCellErrors(
        responseError(400, { non_field_errors: ["Taken."] }),
        "title",
        "Failed",
      ),
    ).toEqual(["Taken."]);
    expect(
      getCellErrors(
        responseError(403, { detail: "Not allowed." }),
        "title",
        "Failed",
      ),
    ).toEqual(["Not allowed."]);
  });

  it("reads a conflict", () => {
    expect(
      getCellErrors(
        responseError(409, {
          conflicts: { views: ["Changed by someone else."] },
          current: { views: 9 },
        }),
        "views",
        "Failed",
      ),
    ).toEqual(["Changed by someone else."]);
  });

  it("falls back without a response", () => {
    expect(getCellErrors(new Error("offline"), "title", "Failed")).toEqual([
      "Failed",
    ]);
  });
});

describe("EditableCell", () => {
  const renderCell = (name: string, value: unknown, error?: string[]) => {
    const onChange = vi.fn();
    const onRevert = vi.fn();

    render(
      <EditableCell
        model={MODEL}
        name={name}
        value={value}
        saving={false}
        saved={false}
        error={error}
        onChange={onChange}
        onRevert={onRevert}
      >
        {String(value)}
      </EditableCell>,
    );

    return { onChange, onRevert };
  };

  it("saves a text cell on Enter", async () => {
    const { onChange } = renderCell("title", "Hello");

    await userEvent.click(screen.getByRole("button", { name: "title" }));
    const input = screen.getByRole("textbox", { name: "title" });
    await userEvent.clear(input);
    await userEvent.type(input, "Hi{Enter}");

    expect(onChange).toHaveBeenCalledWith("Hi");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("sends an emptied number as null", async () => {
    const { onChange } = renderCell("views", 12);

    await userEvent.click(screen.getByRole("button", { name: "views" }));
    await userEvent.clear(screen.getByRole("textbox", { name: "views" }));
    await userEvent.keyboard("{Enter}");

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("puts the old value back on Esc", async () => {
    const { onChange } = renderCell("title", "Hello");

    await userEvent.click(screen.getByRole("button", { name: "title" }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "title" }),
      "x{Escape}",
    );

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "title" })).toHaveTextContent(
      "Hello",
    );
  });

  it("drops a failed value on Esc", async () => {
    const { onRevert } = renderCell("title", "", ["Required."]);

    screen.getByRole("button", { name: "title" }).focus();
    await userEvent.keyboard("{Escape}");

    expect(onRevert).toHaveBeenCalled();
  });

  it("saves a switch on click", async () => {
    const { onChange } = renderCell("featured", false);

    await userEvent.click(screen.getByRole("switch", { name: "featured" }));

    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("shows a failed save's reason", () => {
    renderCell("title", "", ["This field may not be blank."]);

    expect(
      screen.getByRole("img", { name: "This field may not be blank." }),
    ).toBeInTheDocument();
  });
});
