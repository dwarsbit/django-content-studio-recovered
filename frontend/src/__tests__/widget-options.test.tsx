import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WidgetRenderer } from "@/components/widgets/renderer";
import { getDateLimits } from "@/lib/date-limits";
import type { Model, ModelField, WidgetConfig } from "@/types";
import { FieldType, FieldWidget } from "@/types";

const useAdminInfoMock = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: useAdminInfoMock,
}));

function makeModel(fields: Record<string, ModelField>) {
  return {
    label: "testapp.article",
    verbose_name: "Article",
    verbose_name_plural: "Articles",
    tenant_field: null,
    admin: {},
    fields,
  } as unknown as Model;
}

function renderWidget(
  type: FieldType,
  widget: WidgetConfig | null,
  value: unknown = "",
) {
  // The rich text editor reads the discover and links into the studio.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(["model-groups"], {
    models: [],
    media_library: { enabled: true, image_sizes: ["hero"] },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WidgetRenderer
          model={makeModel({ field: { type } })}
          name="field"
          value={value}
          onChange={vi.fn()}
          widget={widget}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("widget options", () => {
  beforeEach(() => {
    useAdminInfoMock.mockReset();
    useAdminInfoMock.mockReturnValue({ data: { widgets: {} } });
  });

  it("passes the default mapping's options to the widget", () => {
    useAdminInfoMock.mockReturnValue({
      data: {
        widgets: {
          [FieldType.CharField]: {
            name: FieldWidget.InputWidget,
            options: { placeholder: "Untitled" },
          },
        },
      },
    });

    renderWidget(FieldType.CharField, null);

    expect(screen.getByRole("textbox")).toHaveAttribute(
      "placeholder",
      "Untitled",
    );
  });

  it("uses the override's options instead of the default mapping's", () => {
    useAdminInfoMock.mockReturnValue({
      data: {
        widgets: {
          [FieldType.CharField]: {
            name: FieldWidget.InputWidget,
            options: { placeholder: "Untitled" },
          },
        },
      },
    });

    renderWidget(FieldType.CharField, { name: FieldWidget.InputWidget });

    expect(screen.getByRole("textbox")).not.toHaveAttribute("placeholder");
  });

  it("renders an input's prefix and suffix around the value", () => {
    renderWidget(FieldType.CharField, {
      name: FieldWidget.InputWidget,
      options: { prefix: "€", suffix: "incl. VAT" },
    });

    expect(screen.getByText("€")).toBeInTheDocument();
    expect(screen.getByText("incl. VAT")).toBeInTheDocument();
  });

  it("makes an input with number limits a number input", () => {
    renderWidget(
      FieldType.IntegerField,
      {
        name: FieldWidget.InputWidget,
        options: { min_value: 0, max_value: 10, step: 2 },
      },
      4,
    );

    const input = screen.getByRole("spinbutton");
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "10");
    expect(input).toHaveAttribute("step", "2");
  });

  it("gives a textarea its rows and placeholder", () => {
    renderWidget(FieldType.TextField, {
      name: FieldWidget.TextAreaWidget,
      options: { rows: 6, placeholder: "Summary" },
    });

    const textarea = screen.getByRole("textbox");
    expect(textarea).toHaveAttribute("rows", "6");
    expect(textarea).toHaveAttribute("placeholder", "Summary");
  });

  it("shows only the rich text features it was given", () => {
    renderWidget(FieldType.TextField, {
      name: FieldWidget.RichTextWidget,
      options: { features: ["bold", "italic"] },
    });

    expect(
      screen.getByLabelText("widgets.rich_text_widget.bold"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("widgets.rich_text_widget.italic"),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("widgets.rich_text_widget.underline"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("widgets.rich_text_widget.bullet_list"),
    ).not.toBeInTheDocument();
    // No block types: no heading menu.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows every rich text feature without a feature list", () => {
    renderWidget(FieldType.TextField, { name: FieldWidget.RichTextWidget });

    expect(
      screen.getByLabelText("widgets.rich_text_widget.underline"),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("offers images and tables with the features", () => {
    renderWidget(FieldType.TextField, {
      name: FieldWidget.RichTextWidget,
      options: { features: ["bold", "image", "table"] },
    });

    expect(
      screen.getByLabelText("widgets.rich_text_widget.insert_image"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("widgets.rich_text_widget.insert_table"),
    ).toBeInTheDocument();
  });

  it("keeps media library images, tables and internal links", async () => {
    const html =
      '<figure class="rich-text-figure align-left">' +
      '<img src="/media/a.jpg" alt="A ridge" width="1600" height="900" data-media-id="7" data-size="hero">' +
      "<figcaption>The ridge</figcaption></figure>" +
      '<p>See <a href="/stories/ferry/" data-link-model="blog.article" data-link-id="12">the ferry</a>.</p>' +
      "<table><tbody><tr><th><p>Leg</p></th></tr><tr><td><p>Oslo</p></td></tr></tbody></table>";
    const onChange = vi.fn();
    const queryClient = new QueryClient();
    queryClient.setQueryData(["model-groups"], {
      models: [],
      media_library: { enabled: true, image_sizes: [] },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <WidgetRenderer
            model={makeModel({ field: { type: FieldType.TextField } })}
            name="field"
            value={html}
            onChange={onChange}
            widget={{ name: FieldWidget.RichTextWidget }}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const content = document.querySelector(".rich-text-field")!;
    // Node views render after the editor mounts.
    const figure = await waitFor(() => {
      const element = content.querySelector("figure.rich-text-figure");
      expect(element).not.toBeNull();
      return element!;
    });
    expect(figure.classList).toContain("align-left");
    expect(figure.querySelector("img")!.getAttribute("src")).toBe(
      "/media/a.jpg",
    );
    expect(content.textContent).toContain("The ridge");
    const link = content.querySelector("a[data-link-model='blog.article']");
    expect(link!.getAttribute("data-link-id")).toBe("12");
    expect(link!.getAttribute("href")).toBe("/stories/ferry/");
    expect(content.querySelector("th")!.textContent).toBe("Leg");
    expect(content.querySelector("td")!.textContent).toBe("Oslo");
  });

  it("strips rich text the features leave out", () => {
    renderWidget(
      FieldType.TextField,
      { name: FieldWidget.RichTextWidget, options: { features: ["bold"] } },
      "<h2>Title</h2><p><strong>bold</strong> <em>italic</em></p>",
    );

    const content = document.querySelector(".rich-text-field")!;
    expect(content.querySelector("strong")).not.toBeNull();
    expect(content.querySelector("h2")).toBeNull();
    expect(content.querySelector("em")).toBeNull();
  });
});

describe("getDateLimits", () => {
  it("disables the days outside the limits", () => {
    const limits = getDateLimits({
      min_date: "2026-01-10",
      max_date: "2026-02-20",
    });

    expect(limits.disabled).toEqual([
      { before: new Date(2026, 0, 10) },
      { after: new Date(2026, 1, 20) },
    ]);
    expect(limits.startMonth).toEqual(new Date(2026, 0, 10));
    expect(limits.endMonth).toEqual(new Date(2026, 1, 20));
  });

  it("limits nothing without options", () => {
    expect(getDateLimits()).toEqual({
      disabled: undefined,
      startMonth: undefined,
      endMonth: undefined,
    });
  });
});
