import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/confirm-dialog-provider";
import { Header } from "@/components/content-editor/header";
import { Dialog } from "@/components/ui/dialog";
import type { Model, Resource } from "@/types";

vi.mock("@/hooks/use-http", () => ({
  useHttp: () => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }),
}));

vi.mock("@/hooks/use-admin-info", () => ({
  useAdminInfo: () => ({ data: { settings: { edited_at_attr: "edited_at" } } }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const model = {
  label: "testapp.article",
  verbose_name: "Article",
  verbose_name_plural: "Articles",
  admin: { is_singleton: false, icon: null, edit: { header: [] }, list: {} },
  fields: {},
} as unknown as Model;

function Form({ children }: { children: ReactNode }) {
  const form = useForm();

  return <FormProvider {...form}>{children}</FormProvider>;
}

function renderHeader(resource?: Resource) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ConfirmDialogProvider>
        <Dialog>
          <Form>
            <Header
              model={model}
              resource={resource}
              resourcePath="/content/testapp.article"
              isSaving={false}
              onSave={async () => {}}
            />
          </Form>
        </Dialog>
      </ConfirmDialogProvider>
    </QueryClientProvider>,
  );
}

describe("View on site", () => {
  it("links to the object's public page in a new tab", () => {
    renderHeader({
      id: "7",
      __str__: "Hello",
      __view_on_site__: "/blog/hello/",
    } as Resource);

    const link = screen.getByRole("link", { name: "editor.view_on_site" });

    expect(link).toHaveAttribute("href", "/blog/hello/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("is hidden without a URL", () => {
    renderHeader({
      id: "7",
      __str__: "Hello",
      __view_on_site__: null,
    } as Resource);

    expect(
      screen.queryByRole("link", { name: "editor.view_on_site" }),
    ).not.toBeInTheDocument();
  });

  it("is hidden for a URL that would run a script", () => {
    renderHeader({
      id: "7",
      __str__: "Hello",
      __view_on_site__: "javascript:alert(document.domain)",
    } as Resource);

    expect(
      screen.queryByRole("link", { name: "editor.view_on_site" }),
    ).not.toBeInTheDocument();
  });

  it("is hidden on the create form", () => {
    renderHeader(undefined);

    expect(
      screen.queryByRole("link", { name: "editor.view_on_site" }),
    ).not.toBeInTheDocument();
  });
});
