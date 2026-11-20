import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordPage } from "@/pages/(auth)/forgot-password/page";
import { LoginPage } from "@/pages/(auth)/login/page";
import { ResetPasswordPage } from "@/pages/(auth)/reset-password/page";
import { FieldType, LoginBackendType } from "@/types";

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));

vi.mock("@/hooks/use-http", () => ({ useHttp: () => httpMock }));
vi.mock("@/auth", () => ({ useAuth: () => ({ setToken: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) =>
      options ? `${key}:${Object.values(options).join(",")}` : key,
  }),
}));

function adminInfo({
  email = true,
  reset = true,
}: { email?: boolean; reset?: boolean } = {}) {
  return {
    site_title: "Northbound",
    password_rules: ["Your password must contain at least 8 characters."],
    password_reset: reset ? { code_minutes: 10 } : null,
    login_backends: [
      {
        type: LoginBackendType.UsernamePassword,
        config: {
          username_field_type: email
            ? FieldType.EmailField
            : FieldType.CharField,
        },
      },
    ],
  };
}

function renderAt(path: string, info = adminInfo()) {
  httpMock.get.mockResolvedValue({ data: info });
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

// input-otp looks for password manager badges; jsdom has no layout.
document.elementFromPoint ??= () => null;

describe("Password reset flow", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("offers a reset on the login page only when it can work", async () => {
    renderAt("/login");
    expect(
      await screen.findByText("login.title:Northbound"),
    ).toBeInTheDocument();
    expect(screen.getByText("login.forgot_password")).toBeInTheDocument();
  });

  it.each([
    ["usernames that are no email", { email: false }],
    ["projects without the reset app", { reset: false }],
  ])("offers no reset for %s", async (_, options) => {
    renderAt("/login", adminInfo(options));
    await screen.findByText("login.title:Northbound");
    expect(screen.queryByText("login.forgot_password")).toBeNull();
  });

  it("explains where to go when a reset is not available", async () => {
    renderAt("/forgot-password", adminInfo({ reset: false }));
    expect(
      await screen.findByText("forgot_password.unavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("login.email")).toBeNull();
  });

  it("sends a code, then asks for it", async () => {
    httpMock.post.mockResolvedValue({ data: null });
    const user = userEvent.setup();
    renderAt("/forgot-password?email=maya%40northbound.example");

    expect(await screen.findByLabelText("login.email")).toHaveValue(
      "maya@northbound.example",
    );
    await user.click(
      screen.getByRole("button", { name: "forgot_password.submit" }),
    );

    expect(httpMock.post).toHaveBeenCalledWith("/password-reset/request", {
      email: "maya@northbound.example",
    });
    expect(await screen.findByText("reset_password.title")).toBeInTheDocument();
    expect(
      screen.getByText("reset_password.code_valid:10"),
    ).toBeInTheDocument();
  });

  it("checks the code, saves the password and returns to log in", async () => {
    httpMock.post.mockResolvedValue({ data: null });
    const user = userEvent.setup();
    renderAt("/reset-password?email=maya%40northbound.example");

    await screen.findByText("reset_password.title");
    await user.type(screen.getByLabelText("reset_password.code"), "482913");

    await waitFor(() =>
      expect(httpMock.post).toHaveBeenCalledWith("/password-reset/code", {
        email: "maya@northbound.example",
        code: "482913",
      }),
    );
    expect(
      await screen.findByText("reset_password.new_title"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Your password must contain at least 8 characters."),
    ).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("reset_password.new"),
      "Lantern-42-north",
    );
    await user.type(
      screen.getByLabelText("reset_password.confirm"),
      "Lantern-42-north",
    );
    await user.click(
      screen.getByRole("button", { name: "reset_password.submit" }),
    );

    expect(httpMock.post).toHaveBeenCalledWith("/password-reset/submit", {
      email: "maya@northbound.example",
      code: "482913",
      password: "Lantern-42-north",
    });
    expect(
      await screen.findByText("login.password_changed"),
    ).toBeInTheDocument();
  });

  it("says when the code is wrong", async () => {
    httpMock.post.mockRejectedValue({
      isAxiosError: true,
      response: { status: 400, data: ["Invalid code."] },
    });
    const user = userEvent.setup();
    renderAt("/reset-password?email=maya%40northbound.example");

    await screen.findByText("reset_password.title");
    await user.type(screen.getByLabelText("reset_password.code"), "000000");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid code.");
    expect(screen.queryByText("reset_password.new_title")).toBeNull();
  });
});
