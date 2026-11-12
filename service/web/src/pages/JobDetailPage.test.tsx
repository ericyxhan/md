import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { JobDetailPage } from "./JobDetailPage";
import { ToastProvider } from "../components/ui/Toast";

// jsdom has no WebGL and no EventSource: both viewer and stream are seams
// that the rest of the page never depends on directly.
vi.mock("../components/viewer/StructureViewport", () => ({
  default: ({ url }: { url: string }) => (
    <div data-testid="mock-viewport" data-url={url} />
  ),
}));
vi.mock("../lib/useJobStream", () => ({
  useJobStream: () => ({ connected: false, liveEvents: [] }),
}));

const JOB_ID = "job-0001";

const queryClient = new QueryClient({
  defaultOptions: {
    // Seeded fixtures stay authoritative: jsdom cannot fetch relative API
    // URLs, so a background refetch would flip the page into its error state.
    queries: { retry: false, staleTime: Infinity },
  },
});

const capabilitiesFixture = {
  api_version: "v1",
  input_modes: ["complex"],
  input_formats: { protein: [".pdb"], ligand: [".pdb"], all: [".pdb"] },
  integrators: ["langevin_middle"],
  barostats: ["none", "monte_carlo"],
  fixed_forcefields: [],
  ligand_forcefield: "",
  defaults: {
    parameterization: {},
    minimization: {},
    equilibration: {},
    production: {},
    integrations: {},
    job: { equilibration_stages: 1, production_enabled: true },
  },
  limits: {
    max_upload_bytes: 50 * 1024 * 1024,
    max_job_upload_bytes: 100 * 1024 * 1024,
    max_ligands: 20,
    max_equilibration_stages: 10,
    max_steps_per_stage: 50_000_000,
    max_total_steps: 200_000_000,
    max_queued_jobs_per_owner: 5,
    min_free_disk_bytes: 512 * 1024 * 1024,
    retention_days: 0,
    rate_limit_requests_per_minute: 120,
    max_name_length: 200,
    max_stage_retries: 3,
    max_preview_bytes: 10 * 1024 * 1024,
    max_preview_atoms: 100_000,
  },
  pdb_download_enabled: true,
  simulation_platform: "CPU",
  views: { enabled: true, max_view_atoms: 25_000 },
  prep_workflows: {
    membrane_embed: {
      enabled: true,
      lipids: ["POPC"],
      max_box_padding_nm: 5.0,
      supported_input_formats: [".pdb"],
    },
  },
};

function jobFixture(status: string) {
  return {
    id: JOB_ID,
    name: "7YAE complex",
    status,
    input_mode: "complex",
    attempt: 1,
    current_stage: "production",
    progress: { step: null, total_steps: null, percent: null, updated_at: null },
    stages: [
      {
        name: "minimization",
        kind: "minimization",
        status: "completed",
        steps_completed: 1000,
        steps_target: 1000,
        attempts: 1,
      },
      {
        name: "production",
        kind: "production",
        status: "completed",
        steps_completed: 500_000,
        steps_target: 500_000,
        attempts: 1,
      },
    ],
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T01:00:00Z",
  };
}

const viewsFixture = (truncated = false) => ({
  items: [
    {
      group: "prepared",
      structure: {
        id: "art-view",
        name: "view.pdb",
        relative_path: "outputs/views/prepared/view.pdb",
        size_bytes: 225_000,
        url: `/api/v1/jobs/${JOB_ID}/artifacts/art-view`,
      },
      trajectory: null,
      manifest: null,
      manifest_data: {
        group: "prepared",
        source: "outputs/metadata/prepared.pdb",
        source_signature: [32_000_000, 1_754_000_000],
        generated_at: "2026-11-01T00:00:00Z",
        source_atoms: 398_753,
        view_atoms: 18_769,
        truncated,
        polymer_atoms: 15_000,
        ligand_atoms: 3_769,
        water_atoms: 1_139_907,
        water_residues: 379_969,
        ion_atoms: 700,
        ions: [
          { name: "CL", count: 355 },
          { name: "NA", count: 345 },
        ],
        ligands: [
          { name: "L01", residues: 139 },
          { name: "L02", residues: 74 },
        ],
        box: { a: 82.3, b: 82.3, c: 82.3, alpha: 90, beta: 90, gamma: 90 },
      },
    },
  ],
});

const router = createMemoryRouter(
  [
    {
      path: "/jobs/:id",
      element: React.createElement(JobDetailPage),
    },
  ],
  { initialEntries: [`/jobs/${JOB_ID}`] }
);

const renderPage = () =>
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  );

describe("JobDetailPage structure tab", () => {
  beforeEach(() => {
    queryClient.clear();

    queryClient.setQueryData(["capabilities"], capabilitiesFixture);
    queryClient.setQueryData(["job", JOB_ID], jobFixture("completed"));
    queryClient.setQueryData(["job", JOB_ID, "events"], []);
    queryClient.setQueryData(["job", JOB_ID, "artifacts"], { items: [] });
    queryClient.setQueryData(["job", JOB_ID, "views"], viewsFixture());
  });

  it("opens completed jobs on the structure view with its composition", async () => {
    renderPage();

    // The viewer chunk resolves asynchronously behind the Suspense boundary.
    const viewport = await screen.findByTestId("mock-viewport");
    expect(viewport.getAttribute("data-url")).toBe(
      `/api/v1/jobs/${JOB_ID}/artifacts/art-view`
    );

    expect(screen.getByText(/398\.8K atoms in the full system/)).toBeTruthy();
    expect(screen.getByText(/including 380K waters/)).toBeTruthy();
    expect(screen.getByText("18.8K")).toBeTruthy(); // solute atoms
    expect(screen.getByText("CL ×355 · NA ×345")).toBeTruthy();
    expect(screen.getByText("L01 ×139 · L02 ×74")).toBeTruthy();
    expect(screen.getByText("82.3 × 82.3 × 82.3 Å")).toBeTruthy();
  });

  it("warns when the solute exceeded the view budget", async () => {
    queryClient.setQueryData(["job", JOB_ID, "views"], viewsFixture(true));

    renderPage();

    await screen.findByTestId("mock-viewport");
    expect(screen.getByText(/view budget of 25K atoms/i)).toBeTruthy();
  });

  it("falls back to activity while running and shows an empty structure tab", () => {
    queryClient.setQueryData(["job", JOB_ID], jobFixture("running"));
    queryClient.setQueryData(["job", JOB_ID, "views"], { items: [] });

    renderPage();

    // Running jobs land on activity, not the structure view.
    expect(screen.queryByTestId("mock-viewport")).toBeNull();
    expect(screen.getByText("Activity")).toBeTruthy();

    fireEvent.click(screen.getByText("Structure"));
    expect(screen.getByText(/No structure view yet/i)).toBeTruthy();
    expect(
      screen.getByText(/appears here as soon as the worker finishes/i)
    ).toBeTruthy();
  });

  it("hides the structure tab when views are disabled", () => {
    queryClient.setQueryData(["capabilities"], {
      ...capabilitiesFixture,
      views: { ...capabilitiesFixture.views, enabled: false },
    });

    renderPage();

    expect(screen.queryByText("Structure")).toBeNull();
    expect(screen.getByText("Activity")).toBeTruthy();
  });
});
