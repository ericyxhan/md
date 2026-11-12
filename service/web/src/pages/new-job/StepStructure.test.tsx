import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StepStructure } from "./StepStructure";
import { createDraft } from "./draft";
import type { Capabilities, FileOut } from "../../lib/types";

// jsdom cannot load the molstar chunk: mock the lazy boundary.
vi.mock("../../components/viewer/lazy", () => ({
  LazyStructureViewport: ({ url }: { url: string }) => (
    <div data-testid="mock-viewport" data-url={url} />
  ),
}));

const capabilities: Capabilities = {
  api_version: "v1",
  input_modes: ["complex"],
  input_formats: { protein: [".pdb"], ligand: [".pdb"], all: [".pdb"] },
  integrators: ["langevin_middle"],
  barostats: ["none", "monte_carlo"],
  fixed_forcefields: [],
  ligand_forcefield: "",
  defaults: {
    parameterization: {
      ph: 7.4,
      padding_nm: 1.0,
      ionic_strength_molar: 0.15,
      add_missing_residues: true,
      allow_undefined_stereo: false,
      max_ligand_residues: 10,
    },
    minimization: { enabled: true },
    equilibration: {},
    production: { enabled: false },
    integrations: { type: "langevin_middle" },
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

function makeFile(overrides: Partial<FileOut> = {}): FileOut {
  return {
    id: "file-001",
    name: "complex.pdb",
    size_bytes: 800_000,
    sha256: "deadbeef",
    content_type: "chemical/x-pdb",
    created_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
});

function renderStep(draft: React.ComponentProps<typeof StepStructure>["draft"]) {
  render(
    <QueryClientProvider client={queryClient}>
      <StepStructure
        draft={draft}
        onChange={vi.fn()}
        capabilities={capabilities as Capabilities}
      />
    </QueryClientProvider>
  );
}

describe("StepStructure upload preview", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("renders a preview card with a viewer for an uploaded complex", async () => {
    const draft = createDraft(capabilities);
    draft.inputMode = "complex";
    draft.complexFile = makeFile();

    renderStep(draft);

    await screen.findByText("Preview");
    const viewport = await screen.findByTestId("mock-viewport");
    expect(viewport.getAttribute("data-url")).toContain(
      "/api/v1/files/file-001/preview",
    );
  });

  it("shows 'not renderable' for an unsupported file type", () => {
    const draft = createDraft(capabilities);
    draft.inputMode = "complex";
    draft.complexFile = makeFile({ name: "script.sh", content_type: "text/x-sh" });

    renderStep(draft);

    expect(screen.getByText(/Not renderable/i)).toBeTruthy();
    expect(screen.queryByTestId("mock-viewport")).toBeNull();
  });
});
