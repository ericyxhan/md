import { describe, it, expect } from "vitest";
import { buildJobCreate, createDraft } from "./draft";
import type { Capabilities } from "../../lib/types";

const capabilities: Capabilities = {
  api_version: "v1",
  input_modes: ["complex"],
  input_formats: { protein: [".pdb"], ligand: [".pdb"], all: [".pdb"] },
  integrators: ["langevin_middle"],
  barostats: ["none", "monte_carlo"],
  precisions: ["mixed", "single", "double"],
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
    min_free_disk_bytes: 0,
    retention_days: 0,
    rate_limit_requests_per_minute: 120,
    max_name_length: 200,
    max_stage_retries: 3,
    max_preview_bytes: 1_000_000,
    max_preview_atoms: 250_000,
  },
  pdb_download_enabled: false,
  simulation_platform: "CUDA",
  views: { enabled: true, max_view_atoms: 25_000 },
  prep_workflows: {
    membrane_embed: {
      enabled: true,
      lipids: ["POPC"],
      max_box_padding_nm: 5.0,
      supported_input_formats: [".pdb"],
    },
  },
} as Capabilities;

describe("buildJobCreate", () => {
  it("carries the selected precision into the request", () => {
    const draft = createDraft(capabilities);
    draft.name = "precision job";
    draft.precision = "double";
    draft.inputMode = "pdb_id";
    draft.pdbId = "1AFO";

    const payload = buildJobCreate(draft);
    expect(payload.precision).toBe("double");
  });

  it("defaults to mixed precision", () => {
    const draft = createDraft(capabilities);
    expect(draft.precision).toBe("mixed");

    const payload = buildJobCreate(draft);
    expect(payload.precision).toBe("mixed");
  });
});
