import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
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

  it("renders the embedding form when prep is enabled", () => {
    renderPage();

    expect(screen.getByText("Membrane embedding")).toBeTruthy();
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

    const submit = screen.getByText(/Start membrane embedding/);
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });
});
