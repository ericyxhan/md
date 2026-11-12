import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import MembraneEmbedPage from "./MembraneEmbedPage";
import { ToastProvider } from "../../components/ui/Toast";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const router = createMemoryRouter(
  [
    { path: "/prep/membrane", element: React.createElement(MembraneEmbedPage) },
  ],
  { initialEntries: ["/prep/membrane"] }
);

const renderPage = () =>
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  );

function setCapabilitiesData(data: any) {
  queryClient.setQueryData(["capabilities"], data);
}

function setPrepJobsData(data: any[]) {
  queryClient.setQueryData(["prep"], data);
}

describe("MembraneEmbedPage", () => {
  beforeEach(() => {
    queryClient.clear();

    setCapabilitiesData({
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
      },
      pdb_download_enabled: true,
      simulation_platform: "CPU",
      prep_workflows: {
        membrane_embed: {
          enabled: true,
          lipids: ["POPC", "POPE"],
          max_box_padding_nm: 5.0,
          supported_input_formats: [".pdb", ".cif", ".mmcif"],
        },
      },
    });
    setPrepJobsData([]);
  });

  it("shows the embedding history first, with a New embedding action", () => {
    renderPage();

    // The list is the page's main content, exactly like the simulations
    // table: history is visible without scrolling.
    expect(screen.getByText("All embeddings")).toBeTruthy();
    expect(screen.getByText("No embeddings yet")).toBeTruthy();
    expect(screen.getAllByText(/New embedding/).length).toBeGreaterThan(0);
  });

  it("opens the embedding form on request", () => {
    renderPage();

    // The form starts closed; the primary action opens it.
    expect(screen.queryByText(/1\. Protein structure/)).toBeNull();
    fireEvent.click(screen.getAllByText(/New embedding/)[0]!);
    expect(screen.getByText(/1\. Protein structure/)).toBeTruthy();
    expect(screen.getByText(/Start membrane embedding/)).toBeTruthy();
  });

  it("shows unavailable message when prep is disabled", () => {
    setCapabilitiesData((prev: any) => ({
      ...prev,
      prep_workflows: {
        membrane_embed: {
          ...prev.prep_workflows.membrane_embed,
          enabled: false,
        },
      },
    }));

    renderPage();

    expect(screen.getByText(/System preparation unavailable/i)).toBeTruthy();
  });

  it("disables submit when no file is selected", () => {
    renderPage();

    fireEvent.click(screen.getAllByText(/New embedding/)[0]!);
    const submit = screen.getByText(/Start membrane embedding/);
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });

  it("survives navigation between the form and a job view", async () => {
    // Regression: the form and the job view used to live in one component
    // behind an early return, so navigating between the two routes changed
    // the number of hooks React saw.  React reports "change in the order of
    // Hooks" and then fails internally ("Expected static flag was missing"),
    // which blanks the page until a refresh.
    const prepJob = {
      id: "job-1",
      type: "membrane_embed",
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

    const navRouter = createMemoryRouter(
      [
        { path: "/prep/membrane", element: React.createElement(MembraneEmbedPage) },
        {
          path: "/prep/membrane/:prepJobId",
          element: React.createElement(MembraneEmbedPage),
        },
      ],
      { initialEntries: ["/prep/membrane"] }
    );

    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <RouterProvider router={navRouter} />
        </ToastProvider>
      </QueryClientProvider>
    );

    expect(screen.getByText("All embeddings")).toBeTruthy();

    // Open the form, then navigate to the job view; the component instance
    // is reused, so a changing hook count would blow up here.
    fireEvent.click(screen.getAllByText(/New embedding/)[0]!);
    expect(screen.getByText(/1\. Protein structure/)).toBeTruthy();

    await act(async () => {
      await navRouter.navigate("/prep/membrane/job-1");
    });

    await waitFor(() => {
      expect(
        screen.getByText("packing POPC.pdb (block 2/9, loop 3/20)")
      ).toBeTruthy();
    });
    expect(screen.getByText("42%")).toBeTruthy();

    // And back again.
    await act(async () => {
      await navRouter.navigate("/prep/membrane");
    });
    await waitFor(() => {
      expect(screen.getByText("All embeddings")).toBeTruthy();
    });

    // The hook order must not have changed across either navigation.
    const hookOrderErrors = consoleError.mock.calls.filter((call) =>
      String(call[0]).includes("order of Hooks"),
    );
    expect(hookOrderErrors).toEqual([]);

    consoleError.mockRestore();
    vi.unstubAllGlobals();
  });
});
