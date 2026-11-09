import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileBox,
  FlaskConical,
  Loader2,
  Terminal,
} from "lucide-react";
import type { Capabilities, JobPlan } from "../../lib/types";
import {
  cn,
  formatBytes,
  formatCompact,
  humanizeStage,
  titleCase,
} from "../../lib/utils";
import { CopyButton } from "../../components/ui/CopyButton";
import {
  simulationNanoseconds,
  stageSteps,
  totalSteps,
  type Draft,
} from "./draft";

function SummaryCard({
  icon,
  title,
  children,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-line bg-surface p-4", className)}>
      <div className="flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
          {icon}
        </span>
        <p className="text-[12.5px] font-semibold text-ink">{title}</p>
      </div>
      <div className="mt-3 space-y-1.5">{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-[12px]">
      <span className="shrink-0 text-muted">{label}</span>
      <span
        className={cn(
          "truncate text-right font-medium text-ink-soft",
          mono && "font-mono text-[11px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function StepReview({
  draft,
  capabilities,
  plan,
  planPending,
  planError,
  planErrorDetails,
  onValidate,
  submitError,
}: {
  draft: Draft;
  capabilities: Capabilities;
  plan?: JobPlan;
  planPending: boolean;
  planError: string | null;
  planErrorDetails?: Record<string, unknown> | null;
  onValidate: () => void;
  submitError: string | null;
}) {
  const totalNs = simulationNanoseconds(draft);
  const steps = totalSteps(draft);
  const errorList = (() => {
    const errors = planErrorDetails?.errors;
    if (!Array.isArray(errors)) return [];
    return errors
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object" && "msg" in entry) {
          return String((entry as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((entry): entry is string => Boolean(entry))
      .slice(0, 6);
  })();

  const planStages = [
    ...(draft.minimization.enabled ? ["Minimization"] : []),
    ...draft.equilibration.map((_, index) => `Equilibration ${index + 1}`),
    ...(draft.productionEnabled ? ["Production"] : []),
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <SummaryCard icon={<FileBox className="size-3.5" />} title="Structure">
          <Row
            label="Input"
            value={
              draft.inputMode === "complex"
                ? "Complex file"
                : draft.inputMode === "pdb_id"
                  ? "PDB download"
                  : "Protein + ligands"
            }
          />
          {draft.inputMode === "complex" ? (
            <Row
              label="File"
              value={draft.complexFile?.name ?? "Not selected"}
            />
          ) : draft.inputMode === "protein_ligands" ? (
            <>
              <Row label="Protein" value={draft.proteinFile?.name ?? "—"} />
              <Row
                label="Ligands"
                value={`${draft.ligandFiles.length} file${draft.ligandFiles.length === 1 ? "" : "s"}`}
              />
            </>
          ) : (
            <Row label="PDB ID" value={draft.pdbId.toUpperCase() || "—"} mono />
          )}
          {draft.inputMode === "complex" && draft.complexFile ? (
            <Row
              label="Size"
              value={formatBytes(draft.complexFile.size_bytes)}
            />
          ) : null}
        </SummaryCard>

        <SummaryCard
          icon={<FlaskConical className="size-3.5" />}
          title="System preparation"
        >
          <Row label="pH" value={draft.parameterization.ph} />
          <Row
            label="Padding"
            value={`${draft.parameterization.padding_nm} nm`}
          />
          <Row
            label="Ionic strength"
            value={`${draft.parameterization.ionic_strength_molar} M`}
          />
          <Row
            label="Missing residues"
            value={
              draft.parameterization.add_missing_residues ? "Rebuild" : "Keep"
            }
          />
          <Row
            label="Undefined stereo"
            value={
              draft.parameterization.allow_undefined_stereo
                ? "Allowed"
                : "Rejected"
            }
          />
        </SummaryCard>

        <SummaryCard icon={<Activity className="size-3.5" />} title="Plan">
          <Row
            label="Stages"
            value={`${planStages.length} · ${planStages[0] ?? "None"}`}
          />
          <Row
            label="Equilibration"
            value={
              draft.equilibration.length
                ? draft.equilibration
                    .map((stage) =>
                      stage.barostat ? `${stage.durationNs} ns NPT` : `${stage.durationNs} ns NVT`,
                    )
                    .join(" → ")
                : "None"
            }
          />
          <Row
            label="Production"
            value={
              draft.productionEnabled
                ? `${draft.production.durationNs} ns`
                : "Disabled"
            }
          />
          <Row
            label="Temperature"
            value={`${draft.equilibration[0]?.temperatureK ?? draft.production.temperatureK} K`}
          />
        </SummaryCard>

        <SummaryCard icon={<Clock3 className="size-3.5" />} title="Estimated run">
          <Row
            label="Simulated time"
            value={totalNs >= 1 ? `${totalNs} ns` : `${(totalNs * 1000).toFixed(0)} ps`}
          />
          <Row label="Integrator steps" value={formatCompact(steps)} mono />
          <Row
            label="Trajectory"
            value={`${formatCompact(
              draft.equilibration.reduce((sum, stage) => sum + stageSteps(stage), 0) +
                (draft.productionEnabled ? stageSteps(draft.production) : 0),
            )} frames`}
          />
          <p className="pt-1 text-[10.5px] leading-relaxed text-faint">
            Wall-clock time depends on system size, GPU, and queue depth.
          </p>
        </SummaryCard>
      </div>

      <div className="rounded-xl border border-line bg-surface">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Terminal className="size-3.5 text-muted" />
            <p className="text-[12.5px] font-semibold text-ink">
              Server validation
            </p>
          </div>
          <button
            type="button"
            onClick={onValidate}
            disabled={planPending}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11.5px] font-medium text-muted transition hover:bg-ink/5 hover:text-ink disabled:opacity-50"
          >
            {planPending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : null}
            {plan ? "Re-validate" : "Validate plan"}
          </button>
        </div>

        <div className="px-4 py-3.5">
          {planPending ? (
            <p className="flex items-center gap-2 text-[12.5px] text-muted">
              <Loader2 className="size-3.5 animate-spin" />
              Checking limits and generating the run configuration…
            </p>
          ) : planError ? (
            <div className="flex items-start gap-2.5 rounded-lg bg-rose-50 p-3 ring-1 ring-inset ring-rose-200/70">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-600" />
              <div className="min-w-0">
                <p className="text-[12.5px] font-medium text-rose-800">
                  {planError}
                </p>
                {errorList.length > 0 ? (
                  <ul className="mt-1.5 space-y-1 text-[11.5px] text-rose-700">
                    {errorList.map((error) => (
                      <li key={error}>• {error}</li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-2 text-[11px] text-rose-700/80">
                  Adjust the plan and validate again. Nothing has been queued.
                </p>
              </div>
            </div>
          ) : plan ? (
            <div>
              <p className="flex items-center gap-2 text-[12.5px] font-medium text-emerald-800">
                <CheckCircle2 className="size-4 text-emerald-600" />
                Plan is valid and within server limits.
              </p>
              <p className="mt-1 text-[11.5px] text-muted">
                {typeof plan.plan.total_steps === "number"
                  ? `${formatCompact(plan.plan.total_steps)} total steps across ${
                      Array.isArray(plan.plan.equilibration)
                        ? plan.plan.equilibration.length
                        : 0
                    } equilibration stage(s)${plan.plan.production ? " and production" : ""}.`
                  : "The server resolved every stage and generated a configuration."}
              </p>

              <details className="group mt-3">
                <summary className="flex cursor-pointer items-center justify-between rounded-lg bg-surface-muted px-3 py-2 text-[11.5px] font-medium text-ink-soft">
                  <span className="inline-flex items-center gap-1.5">
                    <Terminal className="size-3" />
                    Generated config.toml
                  </span>
                  <span className="text-[10.5px] text-faint group-open:hidden">
                    Show
                  </span>
                  <span className="hidden text-[10.5px] text-faint group-open:inline">
                    Hide
                  </span>
                </summary>
                <div className="relative mt-2">
                  <div className="absolute right-1 top-1 z-10">
                    <CopyButton value={plan.config_toml} />
                  </div>
                  <pre className="max-h-64 overflow-auto rounded-lg bg-[#0d1b24] p-3 font-mono text-[10.5px] leading-relaxed text-slate-200">
                    {plan.config_toml}
                  </pre>
                </div>
              </details>
            </div>
          ) : (
            <p className="text-[12px] text-muted">
              Validate the plan to check it against the server&apos;s limits
              before launching. You can still submit directly.
            </p>
          )}

          {submitError ? (
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-rose-50 p-3 ring-1 ring-inset ring-rose-200/70">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-600" />
              <p className="text-[12px] leading-relaxed text-rose-800">
                {submitError}
              </p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex items-start gap-2.5 rounded-xl bg-brand-50/50 px-3.5 py-3 ring-1 ring-inset ring-brand-200/60">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-700" />
        <p className="text-[11.5px] leading-relaxed text-brand-900/80">
          On launch, the job enters the queue and the worker claims it as soon
          as the GPU is free. You can cancel safely at any time; the latest
          checkpoint is preserved. Force fields are fixed at{" "}
          {capabilities.fixed_forcefields.length} protein files and{" "}
          {capabilities.ligand_forcefield}.
        </p>
      </div>
    </div>
  );
}
