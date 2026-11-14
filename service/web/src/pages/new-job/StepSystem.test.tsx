import { useState } from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { Capabilities } from "../../lib/types";
import { createDraft, type Draft } from "./draft";
import { StepSystem } from "./StepSystem";

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
      ligand_charges: {},
      strip_existing_hydrogens: true,
      replace_nonstandard_residues: true,
      strip_crystallographic_waters: false,
      strip_residues: [],
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
  pdb_download_enabled: true,
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
};

function Harness({ onDraft }: { onDraft: (draft: Draft) => void }) {
  const [draft, setDraft] = useState(() => createDraft(capabilities));
  return (
    <>
      <StepSystem
        draft={draft}
        capabilities={capabilities}
        onChange={(next) => {
          setDraft(next);
          onDraft(next);
        }}
      />
      <div data-testid="cleanup-state">
        {JSON.stringify({
          waters: draft.parameterization.strip_crystallographic_waters,
          hydrogens: draft.parameterization.strip_existing_hydrogens,
          nonstandard: draft.parameterization.replace_nonstandard_residues,
          residues: draft.parameterization.strip_residues,
        })}
      </div>
    </>
  );
}

describe("StepSystem preparation cleanup", () => {
  it("updates the water, hydrogen, and nonstandard toggles", () => {
    let latest: Draft | null = null;
    render(<Harness onDraft={(draft) => (latest = draft)} />);

    fireEvent.click(
      screen.getByRole("switch", { name: /remove crystallographic waters/i }),
    );
    fireEvent.click(
      screen.getByRole("switch", { name: /rebuild input hydrogens/i }),
    );
    fireEvent.click(
      screen.getByRole("switch", { name: /replace modified residues/i }),
    );

    expect(latest).not.toBeNull();
    expect(latest!.parameterization.strip_crystallographic_waters).toBe(true);
    expect(latest!.parameterization.strip_existing_hydrogens).toBe(false);
    expect(latest!.parameterization.replace_nonstandard_residues).toBe(false);
  });

  it("parses and normalizes residue names on blur", () => {
    let latest: Draft | null = null;
    render(<Harness onDraft={(draft) => (latest = draft)} />);

    const input = screen.getByLabelText(/residues to remove/i);
    fireEvent.change(input, { target: { value: "so4, GOL  so4" } });
    fireEvent.blur(input);

    expect(latest).not.toBeNull();
    expect(latest!.parameterization.strip_residues).toEqual(["SO4", "GOL"]);
  });
});
