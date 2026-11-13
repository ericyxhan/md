import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AdminJobsPage } from "./AdminJobsPage";
import { AdminSystemPage } from "./AdminSystemPage";
import { AdminAuditPage } from "./AdminAuditPage";

const api = vi.hoisted(() => ({
  listAdminJobs: vi.fn(),
  getAdminSystem: vi.fn(),
  listAdminAudit: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  listAdminJobs: api.listAdminJobs,
  getAdminSystem: api.getAdminSystem,
  listAdminAudit: api.listAdminAudit,
}));

const job = {
  id: "job-1",
  name: "plateau",
  status: "running",
  phase: "simulating",
  input_mode: "complex",
  attempt: 1,
  current_stage: "equil-01",
  progress: { step: 10, total_steps: 100, percent: 10, updated_at: new Date().toISOString() },
  queue_position: null,
  stages: [],
  error: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  queued_at: new Date().toISOString(),
  started_at: new Date().toISOString(),
  completed_at: null,
  owner_id: "00000000-0000-4000-8000-000000000001",
  owner_email: "admin@lattice.local",
  owner_first_name: "Lab",
  owner_last_name: "Administrator",
  stale: false,
} as never;

const systemFixture = {
  generated_at: new Date().toISOString(),
  api_version: "v1",
  database: {
    reachable: true,
    migration: "0009",
    jobs: 4,
    users: 1,
    files: 12,
    audit_events: 12,
    artifacts: 30,
    artifact_bytes: 42_000_000,
  },
  data_root: {
    path: "/data",
    free_bytes: 100_000_000_000,
    min_free_bytes: 536_870_912,
    users_bytes: 500_000_000,
  },
  workers: [
    {
      id: "gpu-0",
      hostname: "labbox",
      gpu_name: "GTX 960",
      version: "0.2.0",
      status: "online",
      current_job_id: null,
      last_heartbeat_at: new Date().toISOString(),
      heartbeat_age_seconds: 2,
      stale: false,
    },
  ],
  queue_counts: { queued: 1, completed: 4 },
};

function renderPage(element: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("admin views", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listAdminJobs.mockResolvedValue({ items: [job], next_cursor: null });
    api.getAdminSystem.mockResolvedValue(systemFixture);
    api.listAdminAudit.mockResolvedValue({
      items: [
        {
          id: 1,
          created_at: new Date().toISOString(),
          owner_id: "00000000-0000-4000-8000-000000000001",
          owner_email: "admin@lattice.local",
          action: "job.create",
          outcome: "accepted",
          target_type: "job",
          target_id: "job-1",
          remote_addr: "127.0.0.1",
          request_id: "req_1",
        },
      ],
      next_cursor: null,
    });
  });

  it("renders the platform queue with the owning account", async () => {
    renderPage(<AdminJobsPage />);
    expect(await screen.findByText("plateau")).toBeInTheDocument();
    expect(screen.getByText(/admin@lattice.local/)).toBeInTheDocument();
  });

  it("renders system health including the worker", async () => {
    renderPage(<AdminSystemPage />);
    expect(await screen.findByText("gpu-0")).toBeInTheDocument();
    expect(screen.getByText("GTX 960")).toBeInTheDocument();
    expect(screen.getByText("Migration")).toBeInTheDocument();
  });

  it("renders the audit trail with the account", async () => {
    renderPage(<AdminAuditPage />);
    expect(await screen.findByText("admin@lattice.local")).toBeInTheDocument();
    // The raw action is in the title attribute; the label is displayed.
    expect(screen.getByTitle("job.create")).toBeInTheDocument();
  });
});
