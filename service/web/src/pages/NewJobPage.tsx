import { useMemo, useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Atom,
  Check,
  FlaskConical,
  Layers,
  Rocket,
  Sparkles,
} from "lucide-react";
import type { Capabilities, FileOut, JobCreate, JobPlan } from "../lib/types";
import { ApiError, createJob, getFile, validateJob } from "../lib/api";
import { useCapabilities } from "../lib/queries";
import { useToast } from "../components/ui/Toast";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import { EmptyState, PageLoader } from "../components/ui/EmptyState";
import { cn, formatCompact, formatSimulationLength } from "../lib/utils";
import {
  buildJobCreate,
  createDraft,
  simulationNanoseconds,
  totalSteps,
  validateDraft,
  type Draft,
} from "./new-job/draft";
import { StepStructure } from "./new-job/StepStructure";
import { StepSystem } from "./new-job/StepSystem";
import { StepSimulation } from "./new-job/StepSimulation";
import { StepReview } from "./new-job/StepReview";

const STEPS = [
  { label: "Structure", description: "Input files", icon: Layers },
  { label: "System", description: "Preparation", icon: FlaskConical },
  { label: "Plan", description: "Dynamics", icon: Atom },
  { label: "Review", description: "Validate & launch", icon: Rocket },
];

function Stepper({
  step,
  onSelect,
}: {
  step: number;
  onSelect: (index: number) => void;
}) {
  return (
    <ol className="mb-4 grid grid-cols-4 gap-1.5">
      {STEPS.map((item, index) => {
        const complete = index < step;
        const active = index === step;
        return (
          <li key={item.label}>
            <button
              type="button"
              onClick={() => onSelect(index)}
              className={cn(
                "group flex w-full flex-col gap-1.5 rounded-lg border px-2.5 py-2 text-left transition sm:flex-row sm:items-center sm:gap-2.5 sm:px-3",
                active
                  ? "border-brand-300 bg-brand-50/60"
                  : "border-transparent hover:border-line hover:bg-surface/70",
              )}
            >
              <span
                className={cn(
                  "flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold transition",
                  complete
                    ? "bg-brand-600 text-white"
                    : active
                      ? "bg-brand-600 text-white"
                      : "bg-ink/[0.07] text-muted",
                )}
              >
                {complete ? <Check className="size-3" /> : index + 1}
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    "block truncate text-[11.5px] font-medium leading-tight",
                    active ? "text-brand-900" : "text-ink-soft",
                  )}
                >
                  {item.label}
                </span>
                <span className="hidden truncate text-[10px] leading-tight text-faint sm:block">
                  {item.description}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function RunSummary({ draft }: { draft: Draft }) {
  const totalNs = simulationNanoseconds(draft);
  const steps = totalSteps(draft);
  const stageCount =
    (draft.minimization.enabled ? 1 : 0) +
    draft.equilibration.length +
    (draft.productionEnabled ? 1 : 0);

  return (
    <div className="card sticky top-6 overflow-hidden">
      <div className="border-b border-line bg-surface-muted/60 px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">
          Run summary
        </p>
      </div>
      <div className="space-y-4 p-4">
        <div>
          <p className="truncate text-[13.5px] font-semibold text-ink">
            {draft.name.trim() || "Untitled simulation"}
          </p>
          <p className="mt-0.5 text-[11px] text-muted">
            {draft.inputMode === "complex"
              ? draft.complexFile?.name ?? "No complex selected"
              : draft.inputMode === "protein_ligands"
                ? draft.proteinFile?.name ?? "No protein selected"
                : draft.pdbId
                  ? `PDB ${draft.pdbId.toUpperCase()}`
                  : "No PDB ID"}
          </p>
        </div>

        <div className="space-y-2 border-t border-line pt-3">
          {[
            {
              label: "Stages",
              value: `${stageCount} stage${stageCount === 1 ? "" : "s"}`,
            },
            {
              label: "Simulated time",
              value:
                totalNs >= 1
                  ? `${totalNs} ns`
                  : `${(totalNs * 1000).toFixed(0)} ps`,
            },
            { label: "Steps", value: formatCompact(steps) },
            { label: "Trajectory", value: formatSimulationLength(steps) },
          ].map((row) => (
            <div
              key={row.label}
              className="flex items-baseline justify-between gap-2 text-[11.5px]"
            >
              <span className="text-muted">{row.label}</span>
              <span className="font-medium text-ink-soft">{row.value}</span>
            </div>
          ))}
        </div>

        {draft.equilibration.length > 0 || draft.productionEnabled ? (
          <div className="border-t border-line pt-3">
            <p className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">
              Timeline
            </p>
            <div className="space-y-1.5">
              {draft.minimization.enabled ? (
                <div className="flex items-center gap-2 text-[11px] text-ink-soft">
                  <span className="size-1.5 rounded-full bg-brand-400" />
                  Minimization
                </div>
              ) : null}
              {draft.equilibration.map((stage, index) => (
                <div
                  key={stage.key}
                  className="flex items-center justify-between gap-2 text-[11px] text-ink-soft"
                >
                  <span className="flex items-center gap-2">
                    <span className="size-1.5 rounded-full bg-sky-400" />
                    Equilibration {index + 1}
                  </span>
                  <span className="text-[10px] text-faint">
                    {stage.durationNs} ns
                  </span>
                </div>
              ))}
              {draft.productionEnabled ? (
                <div className="flex items-center justify-between gap-2 text-[11px] text-ink-soft">
                  <span className="flex items-center gap-2">
                    <span className="size-1.5 rounded-full bg-violet-400" />
                    Production
                  </span>
                  <span className="text-[10px] text-faint">
                    {draft.production.durationNs} ns
                  </span>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="rounded-lg bg-brand-50/60 px-3 py-2.5 ring-1 ring-inset ring-brand-200/50">
          <p className="flex items-center gap-1.5 text-[10.5px] font-semibold text-brand-800">
            <Sparkles className="size-3" />
            What happens next
          </p>
          <p className="mt-1 text-[10.5px] leading-relaxed text-brand-900/70">
            The job is validated, queued, and claimed by the GPU worker. Progress
            streams live to the job page.
          </p>
        </div>
      </div>
    </div>
  );
}

function Wizard({
  capabilities,
  initialPrepFileId,
}: {
  capabilities: Capabilities;
  initialPrepFileId: string | null;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => createDraft(capabilities));
  const [step, setStep] = useState(0);
  const [plan, setPlan] = useState<JobPlan | undefined>();
  const [planError, setPlanError] = useState<string | null>(null);
  const [planErrorDetails, setPlanErrorDetails] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // If arriving from a prep job, pre-select the embedded file as the complex.
  useEffect(() => {
    if (initialPrepFileId && !draft.complexFile) {
      void (async () => {
        try {
          const file = await getFile(initialPrepFileId);
          setDraft((current) => ({
            ...current,
            inputMode: "complex",
            complexFile: file,
          }));
        } catch {
          // Ignore: the file may not exist or be inaccessible.
        }
      })();
    }
  }, [initialPrepFileId, draft.complexFile]);

  const issues = useMemo(() => validateDraft(draft), [draft]);
  const currentIssues = issues.filter((issue) => issue.step === step);
  const canContinue = currentIssues.length === 0;

  const update = (next: Draft) => {
    setDraft(next);
    setPlan(undefined);
    setPlanError(null);
    setPlanErrorDetails(null);
    setSubmitError(null);
  };

  const validateMutation = useMutation({
    mutationFn: (payload: JobCreate) => validateJob(payload),
    onSuccess: (data) => {
      setPlan(data);
      setPlanError(null);
      setPlanErrorDetails(null);
    },
    onError: (error) => {
      setPlan(undefined);
      setPlanError(
        error instanceof Error ? error.message : "Validation failed",
      );
      setPlanErrorDetails(
        error instanceof ApiError ? (error.details ?? null) : null,
      );
    },
  });

  const createMutation = useMutation({
    mutationFn: (payload: JobCreate) => createJob(payload),
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast.push({
        tone: "success",
        title: "Simulation queued",
        description: `${job.name} is waiting for the GPU worker.`,
      });
      navigate(`/jobs/${job.id}`);
    },
    onError: (error) => {
      setSubmitError(
        error instanceof ApiError
          ? `${error.message}${error.requestId ? ` (request ${error.requestId})` : ""}`
          : "Could not create the simulation.",
      );
    },
  });

  const runValidation = () => {
    setSubmitError(null);
    validateMutation.mutate(buildJobCreate(draft));
  };

  const goNext = () => {
    if (!canContinue) return;
    if (step === 2) {
      setStep(3);
      runValidation();
      return;
    }
    setStep((current) => Math.min(current + 1, STEPS.length - 1));
  };

  const launch = () => {
    setSubmitError(null);
    createMutation.mutate(buildJobCreate(draft));
  };

  const payloadIssues = issues.map((issue) => issue.message);

  return (
    <div>
      <PageHeader
        eyebrow="New simulation"
        title="Set up a molecular dynamics run"
        description="Four steps: provide a structure, confirm preparation, choose how long to simulate, then review. Defaults are tuned for a first run."
        actions={
          <Button
            variant="ghost"
            size="md"
            onClick={() => navigate("/jobs")}
            leadingIcon={<ArrowLeft className="size-4" />}
          >
            Back to simulations
          </Button>
        }
      />

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_278px]">
        <div className="min-w-0">
          <Stepper step={step} onSelect={setStep} />

          <Card className="overflow-hidden">
            <div className="border-b border-line px-5 py-4">
              <div className="flex items-center gap-2.5">
                <span className="flex size-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                  {(() => {
                    const Icon = STEPS[step].icon;
                    return <Icon className="size-4" />;
                  })()}
                </span>
                <div>
                  <p className="text-[14px] font-semibold text-ink">
                    {STEPS[step].label}
                  </p>
                  <p className="text-[11.5px] text-muted">
                    {step === 0
                      ? "Choose the protein–ligand system to simulate."
                      : step === 1
                        ? "Confirm protonation, solvent, and force-field preparation."
                        : step === 2
                          ? "Pick a preset or tune individual stages."
                          : "Check the resolved plan and launch the job."}
                  </p>
                </div>
              </div>
            </div>

            <CardBody className="px-5 py-5">
              {step === 0 ? (
                <StepStructure
                  draft={draft}
                  onChange={update}
                  capabilities={capabilities}
                />
              ) : null}
              {step === 1 ? (
                <StepSystem
                  draft={draft}
                  onChange={update}
                  capabilities={capabilities}
                />
              ) : null}
              {step === 2 ? (
                <StepSimulation
                  draft={draft}
                  onChange={update}
                  capabilities={capabilities}
                />
              ) : null}
              {step === 3 ? (
                <StepReview
                  draft={draft}
                  capabilities={capabilities}
                  plan={plan}
                  planPending={validateMutation.isPending}
                  planError={planError}
                  planErrorDetails={planErrorDetails}
                  onValidate={runValidation}
                  submitError={submitError}
                />
              ) : null}
            </CardBody>

            <div className="flex flex-col gap-3 border-t border-line bg-surface-muted/40 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                {!canContinue && currentIssues.length > 0 ? (
                  <p className="text-[11.5px] font-medium text-rose-600">
                    {currentIssues[0].message}
                  </p>
                ) : step === 0 && payloadIssues.length > 0 ? (
                  <p className="text-[11.5px] text-muted">
                    {payloadIssues.length} item
                    {payloadIssues.length === 1 ? "" : "s"} still need attention.
                  </p>
                ) : (
                  <p className="text-[11.5px] text-muted">
                    Step {step + 1} of {STEPS.length} · changes are not saved
                    until you launch.
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => setStep((current) => Math.max(0, current - 1))}
                  disabled={step === 0 || createMutation.isPending}
                >
                  Back
                </Button>
                {step < STEPS.length - 1 ? (
                  <Button
                    variant="primary"
                    size="md"
                    onClick={goNext}
                    disabled={!canContinue}
                    trailingIcon={<ArrowRight className="size-4" />}
                  >
                    {step === 2 ? "Review plan" : "Continue"}
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="md"
                    onClick={launch}
                    loading={createMutation.isPending}
                    disabled={planError !== null || validateMutation.isPending}
                    leadingIcon={<Rocket className="size-4" />}
                  >
                    Launch simulation
                  </Button>
                )}
              </div>
            </div>
          </Card>
        </div>

        <aside className="hidden lg:block">
          <RunSummary draft={draft} />
        </aside>
      </div>
    </div>
  );
}

export function NewJobPage() {
  const capabilities = useCapabilities();
  const [searchParams] = useSearchParams();
  const prepFileId = searchParams.get("prepFileId");
  const navigate = useNavigate();

  if (capabilities.isLoading) {
    return <PageLoader label="Loading workflow capabilities" />;
  }

  if (capabilities.isError || !capabilities.data) {
    return (
      <div className="card mt-10">
        <EmptyState
          icon={<FlaskConical className="size-5" />}
          title="Could not load the workflow"
          description={
            capabilities.error instanceof Error
              ? capabilities.error.message
              : "The service capabilities endpoint is unavailable."
          }
          action={
            <Button onClick={() => void capabilities.refetch()}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <Wizard capabilities={capabilities.data} initialPrepFileId={prepFileId} />
  );
}
