import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider } from "./AuthProvider";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import type { UserInfo } from "../lib/types";

const account: UserInfo = {
  id: "00000000-0000-4000-8000-0000000000aa",
  email: "ada@example.com",
  first_name: "Ada",
  last_name: "Lovelace",
  is_admin: false,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
};

const api = vi.hoisted(() => ({
  getSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getSession: api.getSession,
  login: api.login,
  logout: api.logout,
  register: api.register,
}));

function renderWithAuth(node: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{node}</AuthProvider>
    </QueryClientProvider>,
  );
}

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSession.mockResolvedValue({ authenticated: false });
    api.register.mockResolvedValue(account);
  });

  it("asks for an email address, both names, and a password", async () => {
    renderWithAuth(<RegisterPage onSignIn={() => {}} />);

    expect(screen.getByLabelText("Email address")).toBeInTheDocument();
    expect(screen.getByLabelText("First name")).toBeInTheDocument();
    expect(screen.getByLabelText("Last name")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
  });

  it("creates the account with the details that were typed", async () => {
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage onSignIn={() => {}} />);

    await user.type(screen.getByLabelText("Email address"), "ada@example.com");
    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(api.register).toHaveBeenCalledWith({
        email: "ada@example.com",
        first_name: "Ada",
        last_name: "Lovelace",
        password: "correct horse battery",
      });
    });
  });

  it("refuses to submit when the two passwords differ", async () => {
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage onSignIn={() => {}} />);

    await user.type(screen.getByLabelText("Email address"), "ada@example.com");
    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "something else");

    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/do not match/i)).toBeInTheDocument();
    expect(api.register).not.toHaveBeenCalled();
  });

  it("reports the rejection when the address is already taken", async () => {
    api.register.mockRejectedValue(
      new Error("An account with this email address already exists"),
    );
    const user = userEvent.setup();
    renderWithAuth(<RegisterPage onSignIn={() => {}} />);

    await user.type(screen.getByLabelText("Email address"), "ada@example.com");
    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.type(screen.getByLabelText("Confirm password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(
      await screen.findByText(/already exists/i),
    ).toBeInTheDocument();
  });
});

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSession.mockResolvedValue({ authenticated: false });
    api.login.mockResolvedValue({ authenticated: true, owner: account.id, user: account });
  });

  it("signs in with the email address and the password", async () => {
    const user = userEvent.setup();
    renderWithAuth(<LoginPage onRegister={() => {}} />);

    await user.type(screen.getByLabelText("Email address"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith(
        "ada@example.com",
        "correct horse battery",
      );
    });
  });

  it("does not submit without an email address", async () => {
    const user = userEvent.setup();
    renderWithAuth(<LoginPage onRegister={() => {}} />);

    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(api.login).not.toHaveBeenCalled();
  });

  it("offers a way to create an account", async () => {
    const onRegister = vi.fn();
    const user = userEvent.setup();
    renderWithAuth(<LoginPage onRegister={onRegister} />);

    await user.click(screen.getByRole("button", { name: /create an account/i }));

    expect(onRegister).toHaveBeenCalled();
  });
});
