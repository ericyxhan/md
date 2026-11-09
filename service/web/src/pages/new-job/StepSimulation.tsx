import {
  Check,
  ChevronDown,
  Clock3,
  Gauge,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { Capabilities, IntegratorType } from "../../lib/types";
import {
  cn,
  formatCompact,
  formatSimulationLength,
} from "../../lib/utils";
import {
  Field,
  Select,
  SuffixInput,
  Toggle,
} from "../../components/ui/Form";
import {
  applyPreset,
  makeStage,
  PRESETS,
  simulationNanoseconds,
  stageSteps,
  totalSteps,
  type Draft,
  type StageDraft,
} from "./draft";

const INTEGRATOR_LABELS: Record<string, string> = {
  langevin_middle: "Langevin (recommended)",
  langevin: "Langevin",
  brownian: "Brownian",
  verlet: "Verlet (NVE)",
  nose_hoover: "Nosé–Hoover",
};

function IntegratorFields({
  stage,
  onChange,
  capabilities,
}: {
  stage: StageDraft;
  onChange: (patch: Partial<StageDraft>) => void;
  capabilities: Capabilities;
}) {
  const options = capabilities.integrators.filter(
    (type) => type !== "variable_verlet" && type !== "variable_langevin",
  );
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Integrator">
        <Select
          value={stage.integratorType}
          onChange={(event) =>
            onChange({ integratorType: event.target.value as IntegratorType })
          }
        >
          {options.map((type) => (
            <option key={type} value={type}>
              {INTEGRATOR_LABELS[type] ?? type}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Timestep">
        <SuffixInput
          type="number"
          min={0.0005}
          max={0.01}
          step={0.0005}
          suffix="ps"
          value={stage.timestepPs}
          onChange={(event) =>
            onChange({ timestepPs: Number(event.target.value) })
          }
        />
      </Field>
      {stage.integratorType !== "verlet" ? (
        <Field label="Friction">
          <SuffixInput
            type="number"
            min={0.01}
            max={100}
            step={0.1}
            suffix="ps⁻¹"
            value={stage.frictionPerPs}
            onChange={(event) =>
              onChange({ frictionPerPs: Number(event.target.value) })
            }
          />
        </Field>
      ) : null}
    </div>
  );
}

function StageEditor({
  title,
  stage,
  onChange,
  onRemove,
  capabilities,
}: {
  title: string;
  stage: StageDraft;
  onChange: (patch: Partial<StageDraft>) => void;
  onRemove?: () => void;
  capabilities: Capabilities;
}) {
  return (
    <div className="rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <p className="text-[12.5px] font-semibold text-ink">{title}</p>
        <div className="flex items-center gap-2">
          <span className="mono text-[10.5px] text-faint">
            {formatCompact(stageSteps(stage))} steps
          </span>
          {onRemove ? (
            <button
              type="button"
              onClick={onRemove}
              className="rounded-md p-1.5 text-faint transition hover:bg-rose-50 hover:text-rose-600"
              aria-label="Remove stage"
            >
              <Trash2 className="size-3.5" />
            </button>
          ) : null}
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Duration">
            <SuffixInput
              type="number"
              min={0.001}
              step={0.01}
              suffix="ns"
              value={stage.durationNs}
              onChange={(event) =>
                onChange({ durationNs: Number(event.target.value) })
              }
            />
          </Field>
          <Field label="Temperature">
            <SuffixInput
              type="number"
              min={1}
              max={1000}
              step={1}
              suffix="K"
              value={stage.temperatureK}
              onChange={(event) =>
                onChange({ temperatureK: Number(event.target.value) })
              }
            />
          </Field>
        </div>

        <Toggle
          checked={stage.barostat}
          onChange={(checked) => onChange({ barostat: checked })}
          label="Pressure control (NPT)"
          description="Maintain atmospheric pressure with a Monte Carlo barostat."
        />

        {stage.barostat ? (
          <Field label="Target pressure">
            <SuffixInput
              type="number"
              min={0.1}
              max={100}
              step={0.1}
              suffix="bar"
              value={stage.pressureBar}
              onChange={(event) =>
                onChange({ pressureBar: Number(event.target.value) })
              }
            />
          </Field>
        ) : null}

        <details className="group rounded-lg bg-surface-muted/70 px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between text-[11.5px] font-medium text-muted">
            Advanced integrator settings
            <ChevronDown className="size-3.5 transition group-open:rotate-180" />
          </summary>
          <div className="pt-3">
            <IntegratorFields
              stage={stage}
              onChange={onChange}
              capabilities={capabilities}
            />
          </div>
        </details>
      </div>
    </div>
  );
}

export function StepSimulation({
  draft,
  onChange,
  capabilities,
}: {
  draft: Draft;
  onChange: (next: Draft) => void;
  capabilities: Capabilities;
}) {
  const updateStage = (key: string, patch: Partial<StageDraft>) => {
    onChange({
      ...draft,
      preset: "custom",
      equilibration: draft.equilibration.map((stage) =>
        stage.key === key ? { ...stage, ...patch } : stage,
      ),
    });
  };

  const addStage = () => {
    onChange({
      ...draft,
      preset: "custom",
      equilibration: [
        ...draft.equilibration,
        makeStage({
          durationNs: 0.1,
          label: `Equilibration ${draft.equilibration.length + 1}`,
        }),
      ],
    });
  };

  const removeStage = (key: string) => {
    onChange({
      ...draft,
      preset: "custom",
      equilibration: draft.equilibration.filter((stage) => stage.key !== key),
    });
  };

  const patchProduction = (patch: Partial<StageDraft>) => {
    onChange({
      ...draft,
      preset: "custom",
      production: { ...draft.production, ...patch },
    });
  };

  const totalNs = simulationNanoseconds(draft);
  const steps = totalSteps(draft);

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-2 flex items-center gap-2">
          <Sparkles className="size-4 text-brand-600" />
          <p className="text-[13px] font-semibold text-ink">Choose a preset</p>
        </div>
        <div className="grid gap-2.5 sm:grid-cols-3">
          {PRESETS.map((preset) => {
            const active = draft.preset === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => onChange(applyPreset(draft, preset.id))}
                className={cn(
                  "relative rounded-xl border p-3.5 text-left transition",
                  active
                    ? "border-brand-400 bg-brand-50/55 ring-1 ring-brand-300"
                    : "border-line bg-surface hover:border-brand-200 hover:bg-brand-50/20",
                )}
              >
                {active ? (
                  <span className="absolute right-2.5 top-2.5 flex size-4 items-center justify-center rounded-full bg-brand-600 text-white">
                    <Check className="size-2.5" />
                  </span>
                ) : null}
                <p className="text-[12.5px] font-semibold text-ink">
                  {preset.name}
                </p>
                <p className="mt-0.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-brand-700">
                  {preset.tagline}
                </p>
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">
                  {preset.description}
                </p>
              </button>
            );
          })}
        </div>
        {draft.preset === "custom" ? (
          <p className="mt-2 text-[11px] text-muted">
            Custom plan — adjust any setting below.
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-line bg-surface px-4 py-3.5">
        <Toggle
          checked={draft.minimization.enabled}
          onChange={(enabled) =>
            onChange({
              ...draft,
              minimization: { ...draft.minimization, enabled },
            })
          }
          label="Energy minimization"
          description="Relax clashes before dynamics. Recommended unless the system was already minimized."
        />
        {draft.minimization.enabled ? (
          <div className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
            <Field
              label="Maximum iterations"
              hint="0 lets OpenMM choose a safe limit."
            >
              <SuffixInput
                type="number"
                min={0}
                max={100000}
                value={draft.minimization.max_iterations ?? 0}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    minimization: {
                      ...draft.minimization,
                      max_iterations: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
            <Field label="Tolerance">
              <SuffixInput
                type="number"
                min={0.1}
                max={1000}
                step={0.1}
                suffix="kJ/mol·nm"
                value={draft.minimization.tolerance_kj_mol_nm ?? 10}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    minimization: {
                      ...draft.minimization,
                      tolerance_kj_mol_nm: Number(event.target.value),
                    },
                  })
                }
              />
            </Field>
          </div>
        ) : null}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <div>
            <p className="text-[13px] font-semibold text-ink">
              Equilibration
            </p>
            <p className="mt-0.5 text-[11.5px] text-muted">
              Bring the system to the target temperature and pressure.
            </p>
          </div>
          <button
            type="button"
            onClick={addStage}
            disabled={
              draft.equilibration.length >=
              capabilities.limits.max_equilibration_stages
            }
            className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-[12px] font-medium text-ink-soft transition hover:border-brand-300 hover:text-brand-800 disabled:opacity-40"
          >
            <Plus className="size-3.5" />
            Add stage
          </button>
        </div>

        <div className="space-y-2.5">
          {draft.equilibration.map((stage, index) => (
            <StageEditor
              key={stage.key}
              title={`Equilibration ${index + 1}`}
              stage={stage}
              onChange={(patch) => updateStage(stage.key, patch)}
              onRemove={() => removeStage(stage.key)}
              capabilities={capabilities}
            />
          ))}
          {draft.equilibration.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line-strong px-4 py-5 text-center text-[12px] text-muted">
              No equilibration stages. The production run will start directly
              from the minimized structure.
            </div>
          ) : null}
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3">
          <Toggle
            checked={draft.productionEnabled}
            onChange={(productionEnabled) =>
              onChange({
                ...draft,
                productionEnabled,
                preset: "custom",
              })
            }
            label="Production run"
            description="The sampling stage used for analysis."
          />
        </div>

        {draft.productionEnabled ? (
          <StageEditor
            title="Production"
            stage={draft.production}
            onChange={patchProduction}
            capabilities={capabilities}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl bg-ink/[0.035] px-4 py-3 text-[12px] text-ink-soft">
        <span className="inline-flex items-center gap-1.5">
          <Clock3 className="size-3.5 text-muted" />
          <span className="font-semibold text-ink">
            {totalNs >= 1 ? `${totalNs} ns` : `${(totalNs * 1000).toFixed(0)} ps`}
          </span>
          simulated
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Gauge className="size-3.5 text-muted" />
          <span className="font-semibold text-ink">
            {formatCompact(steps)}
          </span>
          steps
        </span>
        <span className="text-[11px] text-muted">
          ≈ {formatSimulationLength(steps)} of trajectory at 2 fs
        </span>
      </div>
    </div>
  );
}
