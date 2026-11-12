import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import SystemPrepPage from "./SystemPrepPage";
import { ToastProvider } from "../../components/ui/Toast";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function setCapabilitiesData(data: unknown) {
  queryClient.setQueryData(["capabilities"], data);
}

const CAPABILITIES = {
  api_version: "v1",
  input_modes: ["complex"],
  input_formats: { protein: [".pdb"], ligand: [".pdb"], all: [".pdb"] },
  integrators: ["langevin_middle"],
  barostats: ["none", "monte_carlo"],
  fixed_forcefields: ["amber14"],
  ligand_forcefield: "gaff2",
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
  views: { enabled: true, max_view_atoms: 25000 },
  prep_workflows: {
    membrane_embed: {
      enabled: true,
      lipids: ["POPC"],
      max_box_padding_nm: 5.0,
      supported_input_formats: [".pdb"],
    },
  },
};

describe("SystemPrepPage", () => {
  beforeEach(() => {
    queryClient.clear();
    setCapabilitiesData(CAPABILITIES);
    queryClient.setQueryData(["prep"], []);
  });

  it("survives navigation between the form and a job view", async () => {
    // Regression: the form and the job view used to live in one component
    // behind an early return, so navigating between the two routes changed
    // the number of hooks React saw.  React reports "change in the order of
    // Hooks" and then fails internally, which blanks the page until a
    // refresh.
    const prepJob = {
      id: "job-1",
      type: "system_prep",
      status: "running",
      created_at: new Date().toISOString(),
      output_file_ids: [],
      phase: "packing",
      progress_percent: 42,
      progress_message: "packing POPC.pdb (block 2/9, loop 3/20)",
    };

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/prep/jobs/job-1")) {
        return new Response(JSON.stringify(prepJob), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    const router = createMemoryRouter(
      [
        {
          path: "/prep/system-prep",
          element: React.createElement(SystemPrepPage),
        },
        {
          path: "/prep/system-prep/:prepJobId",
          element: React.createElement(SystemPrepPage),
        },
      ],
      { initialEntries: ["/prep/system-prep"] }
    );

    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </QueryClientProvider>
    );

    expect(screen.getByText("All preparations")).toBeTruthy();

    // The form starts closed; the primary action opens it.
    expect(screen.queryByText(/1\. Input structure/)).toBeNull();
    fireEvent.click(screen.getAllByText(/New preparation/)[0]!);
    expect(screen.getByText(/1\. Input structure/)).toBeTruthy();

    await act(async () => {
      await router.navigate("/prep/system-prep/job-1");
    });

    await waitFor(() => {
      expect(
        screen.getByText("packing POPC.pdb (block 2/9, loop 3/20)")
      ).toBeTruthy();
    });

    await act(async () => {
      await router.navigate("/prep/system-prep");
    });
    await waitFor(() => {
      expect(screen.getByText("All preparations")).toBeTruthy();
    });

    const hookOrderErrors = consoleError.mock.calls.filter((call) =>
      String(call[0]).includes("order of Hooks"),
    );
    expect(hookOrderErrors).toEqual([]);

    consoleError.mockRestore();
    vi.unstubAllGlobals();
  });
});
