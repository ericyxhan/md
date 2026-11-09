import type {
  Capabilities,
  FileOut,
  InputMode,
  IntegratorType,
  JobCreate,
  MinimizationSpec,
  ParameterizationSpec,
  StageSpec,
} from "../../lib/types";

export type PresetId = "quick" | "standard" | "production" | "custom";

export interface StageDraft {
  key: string;
  label?: string;
  durationNs: number;
  temperatureK: number;
  barostat: boolean;
  pressureBar: number;
  integratorType: IntegratorType;
  timestepPs: number;
  frictionPerPs: number;
}

export interface Draft {
  name: string;
  preset: PresetId;
  inputMode: InputMode;
  complexFile: FileOut | null;
  proteinFile: FileOut | null;
  ligandFiles: FileOut[];
  pdbId: string;
  parameterization: ParameterizationSpec;
  minimization: MinimizationSpec;
  equilibration: StageDraft[];
  productionEnabled: boolean;
  production: StageDraft;
}

let counter = 0;
export function newStageKey(): string {
  counter += 1;
  return `stage-${Date.now()}-${counter}`;
}

export function makeStage(
  overrides: Partial<StageDraft> = {},
): StageDraft {
  return {
    key: newStageKey(),
    durationNs: 0.1,
    temperatureK: 300,
    barostat: false,
    pressureBar: 1,
    integratorType: "langevin_middle",
    timestepPs: 0.002,
    frictionPerPs: 1,
    ...overrides,
  };
}

export const PRESETS: Array<{
  id: Exclude<PresetId, "custom">;
  name: string;
  tagline: string;
  description: string;
  equilibration: Array<Partial<StageDraft> & { durationNs: number }>;
  productionEnabled: boolean;
  productionNs: number;
}> = [
  {
    id: "quick",
    name: "Quick check",
    tagline: "~1 minute",
    description:
      "A short smoke test that confirms preparation and the GPU worker are healthy.",
    equilibration: [
      {
        durationNs: 0.02,
        label: "Quick equilibration",
        barostat: false,
      },
    ],
    productionEnabled: false,
    productionNs: 0,
  },
  {
    id: "standard",
    name: "Standard run",
    tagline: "Balanced",
    description:
      "Two equilibration phases followed by 10 ns of production. A good default for most systems.",
    equilibration: [
      { durationNs: 0.1, label: "NVT equilibration", barostat: false },
      { durationNs: 0.1, label: "NPT equilibration", barostat: true },
    ],
    productionEnabled: true,
    productionNs: 10,
  },
  {
    id: "production",
    name: "Production",
    tagline: "Long sampling",
    description:
      "A longer NPT production run for analysis. Expect hours depending on system size and GPU.",
    equilibration: [
      { durationNs: 0.5, label: "NPT equilibration", barostat: true },
    ],
    productionEnabled: true,
    productionNs: 100,
  },
];

export function applyPreset(
  draft: Draft,
  presetId: Exclude<PresetId, "custom">,
): Draft {
  const preset = PRESETS.find((item) => item.id === presetId);
  if (!preset) return draft;
  return {
    ...draft,
    preset: preset.id,
    equilibration: preset.equilibration.map((stage) =>
      makeStage({
        barostat: stage.barostat ?? false,
        temperatureK: 300,
        ...stage,
      }),
    ),
    productionEnabled: preset.productionEnabled,
    production: makeStage({
      durationNs: preset.productionNs || 1,
      barostat: true,
      label: "Production",
    }),
    minimization: { ...draft.minimization, enabled: true },
  };
}

export function createDraft(capabilities: Capabilities): Draft {
  const initial = applyPreset(
    {
      name: "",
      preset: "standard",
      inputMode: "complex",
      complexFile: null,
      proteinFile: null,
      ligandFiles: [],
      pdbId: "",
      parameterization: { ...capabilities.defaults.parameterization },
      minimization: {
        ...capabilities.defaults.minimization,
        enabled: true,
      },
      equilibration: [],
      productionEnabled: true,
      production: makeStage({ durationNs: 10, barostat: true }),
    },
    "standard",
  );
  return initial;
}

function round(value: number, places = 6): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

function stagePayload(stage: StageDraft): StageSpec {
  const integrator: StageSpec["integrator"] = {
    type: stage.integratorType,
    timestep_ps: stage.timestepPs,
    temperature_k: stage.temperatureK,
    friction_per_ps: stage.frictionPerPs,
  };
  if (stage.integratorType === "nose_hoover") {
    integrator.collision_frequency_per_ps = 1;
  }
  return {
    ...(stage.label ? { label: stage.label } : {}),
    duration_ps: round(stage.durationNs * 1000),
    report_interval: 1000,
    checkpoint_interval: 1000,
    trajectory_interval: 1000,
    integrator,
    barostat: stage.barostat
      ? {
          type: "monte_carlo",
          pressure_bar: stage.pressureBar,
          frequency: 25,
        }
      : { type: "none" },
  };
}

export function buildJobCreate(draft: Draft): JobCreate {
  let input: JobCreate["input"];
  if (draft.inputMode === "complex") {
    input = {
      mode: "complex",
      complex_file_id: draft.complexFile?.id ?? null,
    };
  } else if (draft.inputMode === "protein_ligands") {
    input = {
      mode: "protein_ligands",
      protein_file_id: draft.proteinFile?.id ?? null,
      ligand_file_ids: draft.ligandFiles.map((file) => file.id),
    };
  } else {
    input = {
      mode: "pdb_id",
      pdb_id: draft.pdbId.trim().toUpperCase(),
    };
  }

  return {
    name: draft.name.trim(),
    input,
    parameterization: draft.parameterization,
    minimization: draft.minimization,
    equilibration: draft.equilibration.map(stagePayload),
    production: draft.productionEnabled
      ? { enabled: true, ...stagePayload(draft.production) }
      : { enabled: false },
  };
}

export function stageSteps(stage: StageDraft): number {
  return Math.max(1, Math.round((stage.durationNs * 1000) / stage.timestepPs));
}

export function totalSteps(draft: Draft): number {
  return (
    draft.equilibration.reduce((sum, stage) => sum + stageSteps(stage), 0) +
    (draft.productionEnabled ? stageSteps(draft.production) : 0)
  );
}

export function simulationNanoseconds(draft: Draft): number {
  return (
    draft.equilibration.reduce((sum, stage) => sum + stage.durationNs, 0) +
    (draft.productionEnabled ? draft.production.durationNs : 0)
  );
}

export interface StepIssue {
  step: number;
  message: string;
}

export function validateDraft(draft: Draft): StepIssue[] {
  const issues: StepIssue[] = [];
  if (!draft.name.trim()) {
    issues.push({ step: 0, message: "Give the simulation a name." });
  }
  if (draft.inputMode === "complex" && !draft.complexFile) {
    issues.push({ step: 0, message: "Upload a protein–ligand complex file." });
  }
  if (draft.inputMode === "protein_ligands") {
    if (!draft.proteinFile) {
      issues.push({ step: 0, message: "Upload a protein structure." });
    }
    if (draft.ligandFiles.length === 0) {
      issues.push({ step: 0, message: "Add at least one ligand file." });
    }
  }
  if (draft.inputMode === "pdb_id") {
    if (!/^[0-9a-z]{4}$/i.test(draft.pdbId.trim())) {
      issues.push({ step: 0, message: "Enter a four-character PDB ID." });
    }
  }
  if (draft.equilibration.length === 0 && !draft.productionEnabled) {
    issues.push({
      step: 2,
      message: "Enable equilibration or production.",
    });
  }
  for (const stage of draft.equilibration) {
    if (stage.durationNs <= 0) {
      issues.push({
        step: 2,
        message: "Equilibration durations must be greater than zero.",
      });
    }
  }
  if (draft.productionEnabled && draft.production.durationNs <= 0) {
    issues.push({
      step: 2,
      message: "Production duration must be greater than zero.",
    });
  }
  return issues;
}
