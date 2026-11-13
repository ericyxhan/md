import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider } from "../auth/AuthProvider";
import { AccountPage } from "./AccountPage";
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
  updateMe: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  getSession: api.getSession,
  login: api.login,
  logout: api.logout,
  register: api.register,
  updateMe: api.updateMe,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AccountPage />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("AccountPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSession.mockResolvedValue({ authenticated: true, user: account });
    api.updateMe.mockResolvedValue(account);
  });

  it("shows the details of the signed-in account", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("Email address")).toHaveValue(
        "ada@example.com",
      );
    });
    expect(screen.getByLabelText("First name")).toHaveValue("Ada");
    expect(screen.getByLabelText("Last name")).toHaveValue("Lovelace");
  });

  it("saves the details that were edited", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("First name")).toHaveValue("Ada");
    });

    const firstName = screen.getByLabelText("First name");
    await user.clear(firstName);
    await user.type(firstName, "Augusta");
    await user.click(screen.getByRole("button", { name: /save details/i }));

    await waitFor(() => {
      expect(api.updateMe).toHaveBeenCalledWith({
        first_name: "Augusta",
        last_name: "Lovelace",
        email: "ada@example.com",
      });
    });
  });

  it("sends the current password along with a new one", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Current password"),
      "correct horse battery",
    );
    await user.type(screen.getByLabelText("New password"), "a brand new password");
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "a brand new password",
    );
    await user.click(screen.getByRole("button", { name: /change password/i }));

    await waitFor(() => {
      expect(api.updateMe).toHaveBeenCalledWith({
        password: "a brand new password",
        current_password: "correct horse battery",
      });
    });
  });

  it("refuses to send a new password that does not match the confirmation", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Current password"),
      "correct horse battery",
    );
    await user.type(screen.getByLabelText("New password"), "a brand new password");
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "something else",
    );
    await user.click(screen.getByRole("button", { name: /change password/i }));

    expect(await screen.findByText(/do not match/i)).toBeInTheDocument();
    expect(api.updateMe).not.toHaveBeenCalled();
  });

  it("reports a rejected change", async () => {
    api.updateMe.mockRejectedValue(
      new Error("The current password is not correct"),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText("Current password"),
      "correct horse battery",
    );
    await user.type(screen.getByLabelText("New password"), "a brand new password");
    await user.type(
      screen.getByLabelText("Confirm new password"),
      "a brand new password",
    );
    await user.click(screen.getByRole("button", { name: /change password/i }));

    expect(
      await screen.findByText(/current password is not correct/i),
    ).toBeInTheDocument();
  });
});
