import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AdminUsersPage } from "./AdminUsersPage";
import type { AdminUserInfo } from "../lib/types";

const administrator: AdminUserInfo = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "admin@lattice.local",
  first_name: "Lab",
  last_name: "Administrator",
  is_admin: true,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
  updated_at: "2026-01-01T00:00:00Z",
  usage: { jobs: 3, files: 2, prep_jobs: 1 },
};

const member: AdminUserInfo = {
  id: "00000000-0000-4000-8000-0000000000aa",
  email: "ada@example.com",
  first_name: "Ada",
  last_name: "Lovelace",
  is_admin: false,
  is_active: true,
  created_at: "2026-01-02T00:00:00Z",
  last_login_at: null,
  updated_at: "2026-01-02T00:00:00Z",
  usage: { jobs: 0, files: 0, prep_jobs: 0 },
};

const api = vi.hoisted(() => ({
  listUsers: vi.fn(),
  adminUpdateUser: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  listUsers: api.listUsers,
  adminUpdateUser: api.adminUpdateUser,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminUsersPage />
    </QueryClientProvider>,
  );
}

describe("AdminUsersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listUsers.mockResolvedValue([administrator, member]);
    api.adminUpdateUser.mockImplementation(
      async (_id: string, payload: { is_active?: boolean }) => ({
        ...member,
        is_active: payload.is_active ?? member.is_active,
      }),
    );
  });

  it("lists every account with its usage", async () => {
    renderPage();

    expect(await screen.findByText(/ada@example\.com/)).toBeInTheDocument();
    expect(screen.getByText(/admin@lattice\.local/)).toBeInTheDocument();
    expect(screen.getByText(/Ada Lovelace/)).toBeInTheDocument();
    // The administrator's row carries its own usage counts.
    expect(screen.getByText(/3 jobs/)).toBeInTheDocument();
  });

  it("deactivates an account", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(/ada@example\.com/);
    // Every row has its own buttons, so the one that belongs to the new
    // account is the one that has to be clicked.
    const row = screen.getByText(/ada@example\.com/).closest(".flex-wrap");
    expect(row).not.toBeNull();
    await user.click(
      within(row as HTMLElement).getByRole("button", { name: /deactivate/i }),
    );

    await waitFor(() => {
      expect(api.adminUpdateUser).toHaveBeenCalledWith(member.id, {
        is_active: false,
      });
    });
  });

  it("promotes an account to administrator", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(/ada@example\.com/);
    await user.click(screen.getByRole("button", { name: /make admin/i }));

    await waitFor(() => {
      expect(api.adminUpdateUser).toHaveBeenCalledWith(member.id, {
        is_admin: true,
      });
    });
  });

  it("reports a rejected change", async () => {
    api.adminUpdateUser.mockRejectedValue(new Error("Account not found"));
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(/ada@example\.com/);
    await user.click(screen.getByRole("button", { name: /make admin/i }));

    expect(await screen.findByText(/account not found/i)).toBeInTheDocument();
  });
});
