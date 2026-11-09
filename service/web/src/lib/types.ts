/**
 * Wire types for the v1 public API.
 *
 * The API is the source of truth.  These types mirror
 * `service/api/app/schemas.py`; keep them in sync when the contract changes.
 */

export type JobStatus =
  | "queued"
  | "claimed"
  | "running"
  | "canceling"
  | "completed"
  | "failed"
  | "canceled";

export type StageStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "canceled";

export type InputMode = "complex" | "protein_ligands" | "pdb_id";

export type IntegratorType =
  | "langevin_middle"
  | "langevin"
  | "brownian"
  | "verlet"
  | "variable_verlet"
  | "variable_langevin"
  | "nose_hoover";

export type BarostatType = "none" | "monte_carlo";

export interface Capabilities {
  api_version: string;
  input_modes: InputMode[];
  input_formats: {
    protein: string[];
    ligand: string[];
    all: string[];
  };
  integrators: IntegratorType[];
  barostats: BarostatType[];
  fixed_forcefields: string[];
  ligand_forcefield: string;
  defaults: {
    parameterization: ParameterizationSpec;
    minimization: MinimizationSpec;
    equilibration: StageSpec;
    production: ProductionSpec;
    integrations: IntegratorSpec;
    job: {
      equilibration_stages: number;
      production_enabled: boolean;
    };
  };
  limits: {
    max_upload_bytes: number;
    max_job_upload_bytes: number;
    max_ligands: number;
    max_equilibration_stages: number;
    max_steps_per_stage: number;
    max_total_steps: number;
    max_queued_jobs_per_owner: number;
    min_free_disk_bytes: number;
    retention_days: number;
    rate_limit_requests_per_minute: number;
    max_name_length: number;
    max_stage_retries: number;
  };
  pdb_download_enabled: boolean;
  simulation_platform: string;
  prep_workflows: {
    membrane_embed: {
      enabled: boolean;
      lipids: LipidType[];
      max_box_padding_nm: number;
      supported_input_formats: string[];
    };
  };
}

export interface FileOut {
  id: string;
  name: string;
  size_bytes: number;
  sha256: string;
  content_type: string;
  created_at: string;
}

export interface IntegratorSpec {
  type: IntegratorType;
  timestep_ps?: number | null;
  temperature_k?: number | null;
  friction_per_ps?: number | null;
  collision_frequency_per_ps?: number | null;
  error_tolerance?: number | null;
  maximum_step_ps?: number | null;
  constraint_tolerance?: number | null;
  integration_force_groups?: number | null;
  random_seed?: number | null;
}

export interface BarostatSpec {
  type: BarostatType;
  pressure_bar?: number;
  temperature_k?: number | null;
  frequency?: number;
  random_seed?: number | null;
}

export interface StageFields {
  label?: string | null;
  steps?: number | null;
  duration_ps?: number | null;
  duration_ns?: number | null;
  report_interval?: number;
  trajectory_interval?: number | null;
  checkpoint_interval?: number;
  retries?: number;
  retry_delay_s?: number;
  initial_velocity_temperature_k?: number | null;
  velocity_seed?: number | null;
  integrator?: IntegratorSpec;
  barostat?: BarostatSpec;
}

export type StageSpec = StageFields;

export interface ProductionSpec extends StageFields {
  enabled: boolean;
}

export interface MinimizationSpec {
  enabled: boolean;
  max_iterations?: number;
  tolerance_kj_mol_nm?: number;
}

export interface ParameterizationSpec {
  ph: number;
  padding_nm: number;
  ionic_strength_molar: number;
  add_missing_residues: boolean;
  allow_undefined_stereo: boolean;
  max_ligand_residues: number;
}

export interface InputSpec {
  mode: InputMode;
  complex_file_id?: string | null;
  protein_file_id?: string | null;
  ligand_file_ids?: string[];
  pdb_id?: string | null;
}

export interface JobCreate {
  name: string;
  input: InputSpec;
  parameterization?: ParameterizationSpec;
  minimization?: MinimizationSpec;
  equilibration?: StageSpec[];
  production?: ProductionSpec;
}

export interface StageOut {
  name: string;
  kind: string;
  status: StageStatus;
  steps_completed: number;
  steps_target: number;
  attempts: number;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ProgressOut {
  step?: number | null;
  total_steps?: number | null;
  percent?: number | null;
  updated_at?: string | null;
}

export interface JobError {
  code: string;
  message: string;
}

export interface Job {
  id: string;
  name: string;
  status: JobStatus;
  phase?: string | null;
  input_mode: InputMode;
  attempt: number;
  current_stage?: string | null;
  progress: ProgressOut;
  queue_position?: number | null;
  stages: StageOut[];
  error?: JobError | null;
  created_at: string;
  updated_at: string;
  queued_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface JobList {
  items: Job[];
  next_cursor?: string | null;
}

export interface JobEvent {
  id: number;
  type: string;
  message: string;
  data?: Record<string, unknown> | null;
  created_at: string;
}

export interface Artifact {
  id: string;
  stage_name?: string | null;
  kind: string;
  relative_path: string;
  name: string;
  size_bytes: number;
  content_type: string;
  created_at: string;
}

export interface ArtifactList {
  items: Artifact[];
}

export interface LogEntry {
  name: string;
  relative_path: string;
  size_bytes: number;
  content_type: string;
  updated_at: string;
}

export interface LogList {
  items: LogEntry[];
}

export interface LogTail {
  name: string;
  relative_path: string;
  content: string;
  lines: number;
  truncated: boolean;
  size_bytes: number;
}

export interface JobPlan {
  valid: boolean;
  config_toml: string;
  plan: Record<string, unknown>;
}

export interface JobSpec {
  version: number;
  name: string;
  input: Record<string, unknown>;
  parameterization: ParameterizationSpec;
  minimization: MinimizationSpec;
  equilibration: Array<Record<string, unknown>>;
  production: Record<string, unknown> | null;
  total_steps: number;
}

export interface SessionInfo {
  authenticated: boolean;
  owner?: string | null;
  issued_at?: string | null;
  expires_at?: string | null;
  auth_method?: string | null;
}

export type RetryMode =
  | "resume"
  | "restart"
  | "restart_stage"
  | "reparameterize";

// ---------------------------------------------------------------------------
// System preparation: membrane embedding
// ---------------------------------------------------------------------------

export type LipidType =
  | "POPC"
  | "POPE"
  | "DPPC"
  | "DLPC"
  | "DSPC"
  | "SOPC";

export interface MembraneEmbedRequest {
  protein_file_id: string;
  lipid: LipidType;
  box_padding_nm: number;
  orientation?: string | null;
  ionic_strength_molar: number;
}

export interface MembraneEmbedOut {
  prep_job_id: string;
  status: string;
  embedded_pdb_file_id: string | null;
  topology_file_id: string | null;
  error: string | null;
}

export interface PrepJobStatus {
  id: string;
  type: string;
  status: "queued" | "claimed" | "running" | "completed" | "failed" | "canceled";
  created_at: string;
  completed_at?: string | null;
  output_file_ids: string[];
  error?: string | null;
  phase?: string | null;
  progress_percent?: number | null;
  progress_updated_at?: string | null;
  cancel_requested?: boolean;
}

export type SystemPrepOperation = "remove_ligand" | "select_chain" | "add_ligand";

export interface SystemPrepStep {
  operation: SystemPrepOperation;
  ligand_to_remove?: string | null;
  chain_to_keep?: string | null;
  ligand_file_ids?: string[];
}

export interface SystemPrepRequest {
  name: string;
  input_file_id?: string | null;
  pdb_id?: string | null;
  steps: SystemPrepStep[];
}

export interface SystemPrepOut {
  prep_job_id: string;
  status: string;
  output_file_ids: string[];
  error?: string | null;
}

export interface PDBInspection {
  chains: Record<string, string[]>;
  ligands: string[];
}
