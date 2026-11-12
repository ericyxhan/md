import { Suspense, lazy, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Atom,
  Ban,
  CircleDot,
  Clock3,
  Database,
  Droplets,
  FileCode2,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Terminal,
  Thermometer,
} from "lucide-react";
import type { Job, JobEvent, RetryMode, ViewManifest } from "../lib/types";
import { ApiError, cancelJob, retryJob } from "../lib/api";
import {
  useArtifacts,
  useCapabilities,
  useJob,
  useJobConfig,
  useJobEvents,
  useJobSpec,
  useJobViews,
} from "../lib/queries";
import { useJobStream } from "../lib/useJobStream";
import { useToast } from "../components/ui/Toast";
import { AnalysisPanel } from "../components/analysis/AnalysisPanel";
import { LazyStructureViewport } from "../components/viewer/lazy";
import { Button } from "../components/ui/Button";
import { Badge, StatusBadge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { CopyButton } from "../components/ui/CopyButton";
import { EmptyState, PageLoader, Spinner } from "../components/ui/EmptyState";
import { Modal } from "../components/ui/Modal";
import { ProgressBar, ProgressRing } from "../components/ui/Progress";
import { Select } from "../components/ui/Form";
import { EventFeed } from "../components/jobs/EventFeed";
import { StageTimeline } from "../components/jobs/StageTimeline";
import { ArtifactTable } from "../components/jobs/ArtifactTable";
import { LogViewer } from "../components/jobs/LogViewer";
import {
  cn,
  elapsedSeconds,
  formatCompact,
  formatDateTime,
  formatDuration,
  formatRelative,
  humanizeStage,
  isActive,
  isTerminal,
  jobPercent,
  titleCase,
} from "../lib/utils";

type Tab =
  | "structure"
  | "activity"
  | "artifacts"
  | "logs"
  | "configuration"
  | "analysis";

function ionSummary(manifest: ViewManifest): string {
  return manifest.ions.length
    ? manifest.ions
        .map((ion) => `${ion.name} ×${formatCompact(ion.count)}`)
        .join(" · ")
    : "—";
}

function ligandSummary(manifest: ViewManifest): string {
  return manifest.ligands.length
    ? manifest.ligands
        .map((ligand) => `${ligand.name} ×${ligand.residues}`)
        .join(" · ")
    : "—";
}

function boxSummary(manifest: ViewManifest): string {
  const box = manifest.box;
  if (!box) return "—";
  return `${box.a.toFixed(1)} × ${box.b.toFixed(1)} × ${box.c.toFixed(1)} Å`;
}

function StructurePanel({
  jobId,
  poll,
  maxViewAtoms,
}: {
  jobId: string;
  poll: boolean;
  maxViewAtoms?: number;
}) {
  const views = useJobViews(jobId, true, poll);

  if (views.isLoading) {
    return (
      <div className="flex items-center gap-2 px-5 py-8 text-[12.5px] text-muted">
        <Spinner /> Loading structure
      </div>
    );
  }

  if (views.isError) {
    return (
      <div className="px-5 py-8">
        <EmptyState
          icon={<AlertTriangle className="size-5" />}
          title="Structure views unavailable"
          description={
            views.error instanceof Error
              ? views.error.message
              : "The view inventory could not be loaded."
          }
        />
      </div>
    );
  }

  const prepared = views.data?.items.find((view) => view.group === "prepared");

  if (!prepared?.structure) {
    return (
      <EmptyState
        icon={<Atom className="size-5" />}
        title="No structure view yet"
        description={
          poll
            ? "The built system appears here as soon as the worker finishes preparing it."
            : "This run has no derived structure view. Raw artifacts remain available in the Artifacts tab."
        }
      />
    );
  }

  const manifest = prepared.manifest_data;

  return (
    <div className="px-5 py-4">
      <div className="h-[420px] overflow-hidden rounded-xl border border-line bg-surface sm:h-[500px]">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center gap-2 text-[12.5px] text-muted">
              <Spinner /> Loading viewer
            </div>
          }
        >
          <LazyStructureViewport
            url={prepared.structure.url}
            label={prepared.structure.name}
          />
        </Suspense>
      </div>

      {manifest ? (
        <>
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted">
            Built system with solvent removed for display —{" "}
            {formatCompact(manifest.source_atoms)} atoms in the full system
            {manifest.water_residues
              ? `, including ${formatCompact(manifest.water_residues)} waters`
              : ""}
            {manifest.ion_atoms
              ? ` and ${formatCompact(manifest.ion_atoms)} ion atoms`
              : ""}
            . Raw artifacts stay downloadable from the Artifacts tab.
          </p>

          {manifest.truncated ? (
            <p className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
              The solute exceeds the view budget
              {maxViewAtoms
                ? ` of ${formatCompact(maxViewAtoms)} atoms`
                : ""}
              ; later atoms are hidden from this view.
            </p>
          ) : null}

          <div className="mt-3 grid grid-cols-2 gap-3 border-t border-line pt-4 sm:grid-cols-3 lg:grid-cols-6">
            <Metric
              label="Solute atoms"
              value={formatCompact(manifest.view_atoms)}
            />
            <Metric
              label="System atoms"
              value={formatCompact(manifest.source_atoms)}
            />
            <Metric
              label="Waters removed"
              value={formatCompact(manifest.water_residues)}
            />
            <Metric label="Ions" value={ionSummary(manifest)} />
            <Metric label="Ligands" value={ligandSummary(manifest)} />
            <Metric label="Box" value={boxSummary(manifest)} />
          </div>
        </>
      ) : (
        <p className="mt-3 text-[12.5px] text-muted">
          {prepared.structure.name} — a solute-focused view of the built
          system.
        </p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-faint">
        {label}
      </p>
      <p className="mt-1 truncate text-[12.5px] font-medium text-ink-soft">
        {value}
      </p>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-[12px]">
      <span className="shrink-0 text-muted">{label}</span>
      <span
        className={cn(
          "min-w-0 truncate text-right font-medium text-ink-soft",
          mono && "font-mono text-[11px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function ProgressPanel({ job }: { job: Job }) {
  const percent = jobPercent(job);
  const elapsed = elapsedSeconds(job.started_at, job.completed_at);
  const eta =
    elapsed && percent > 0.5 && percent < 100
      ? (elapsed * (100 - percent)) / percent
      : null;

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">
            Overall progress
          </p>
          <div className="mt-2 flex flex-wrap items-baseline gap-2.5">
            <span className="text-[34px] font-semibold leading-none tracking-[-0.04em] text-ink tabular-nums">
              {Math.round(percent)}%
            </span>
            <StatusBadge status={job.status} />
          </div>
          <p className="mt-2 text-[12.5px] text-muted">
            {job.current_stage
              ? humanizeStage(job.current_stage)
              : job.status === "queued"
                ? `Waiting for the worker · position ${job.queue_position ?? "—"}`
                : job.status === "completed"
                  ? "All stages finished"
                  : "Awaiting stage report"}
          </p>
        </div>
        <ProgressRing
          value={percent}
          size={82}
          stroke={7}
          tone={
            job.status === "failed"
              ? "rose"
              : job.status === "completed"
                ? "green"
                : "brand"
          }
          label={`${Math.round(percent)}%`}
        />
      </div>

      <ProgressBar
        value={percent}
        className="mt-4 h-2"
        tone={
          job.status === "failed"
            ? "rose"
            : job.status === "completed"
              ? "green"
              : "brand"
        }
        animated={isActive(job.status) && percent < 100}
      />

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 sm:grid-cols-4">
        <Metric
          label="Step"
          value={
            job.progress?.step != null
              ? `${formatCompact(job.progress.step)} / ${formatCompact(job.progress.total_steps)}`
              : "—"
          }
        />
        <Metric label="Elapsed" value={formatDuration(elapsed)} />
        <Metric
          label={eta ? "Est. remaining" : "Attempt"}
          value={eta ? formatDuration(eta) : `#${job.attempt}`}
        />
        <Metric label="Updated" value={formatRelative(job.updated_at)} />
      </div>
    </Card>
  );
}

function ConfigurationPanel({ jobId }: { jobId: string }) {
  const [tab, setTab] = useState<"toml" | "spec">("toml");
  const spec = useJobSpec(jobId);
  const config = useJobConfig(jobId);

  const content =
    tab === "toml"
      ? config.data ?? ""
      : spec.data
        ? JSON.stringify(spec.data, null, 2)
        : "";

  return (
    <div>
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex gap-1">
          {(
            [
              { id: "toml" as const, label: "config.toml" },
              { id: "spec" as const, label: "Resolved spec" },
            ]
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11.5px] font-medium transition",
                tab === item.id
                  ? "bg-ink text-white"
                  : "text-muted hover:bg-ink/5 hover:text-ink",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        {content ? <CopyButton value={content} /> : null}
      </div>
      <div className="p-4">
        {config.isLoading || spec.isLoading ? (
          <div className="flex items-center gap-2 text-[12.5px] text-muted">
            <Spinner /> Loading configuration
          </div>
        ) : content ? (
          <pre className="max-h-[520px] overflow-auto rounded-lg bg-[#0d1b24] p-4 font-mono text-[11px] leading-relaxed text-slate-200">
            {content}
          </pre>
        ) : (
          <p className="text-[12.5px] text-muted">
            This job has no readable configuration.
          </p>
        )}
      </div>
    </div>
  );
}

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const toast = useToast();
  const capabilities = useCapabilities();
  const jobQuery = useJob(id);
  const eventsQuery = useJobEvents(id);
  const { connected, liveEvents } = useJobStream(id);
  const artifacts = useArtifacts(id, true);
  const [selectedTab, setSelectedTab] = useState<Tab | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [retryOpen, setRetryOpen] = useState(false);

  const job = jobQuery.data;

  const events = useMemo(() => {
    const byId = new Map<number, JobEvent>();
    for (const event of eventsQuery.data ?? []) byId.set(event.id, event);
    for (const event of liveEvents) byId.set(event.id, event);
    return Array.from(byId.values()).sort((a, b) => b.id - a.id);
  }, [eventsQuery.data, liveEvents]);

  const cancelMutation = useMutation({
    mutationFn: () => cancelJob(id as string),
    onSuccess: () => {
      setCancelOpen(false);
      toast.push({
        tone: "info",
        title: "Stop requested",
        description:
          "The worker will preserve the latest checkpoint and stop gracefully.",
      });
      void queryClient.invalidateQueries({ queryKey: ["job", id] });
    },
    onError: (error) => {
      toast.push({
        tone: "error",
        title: "Could not stop the simulation",
        description:
          error instanceof Error ? error.message : "Unknown error",
      });
    },
  });

  if (jobQuery.isLoading) {
    return <PageLoader label="Loading simulation" />;
  }

  if (jobQuery.isError || !job) {
    return (
      <div className="card mt-8">
        <EmptyState
          icon={<AlertTriangle className="size-5" />}
          title="Simulation not found"
          description={
            jobQuery.error instanceof Error
              ? jobQuery.error.message
              : "This run may have been removed by retention."
          }
          action={
            <Link to="/jobs">
              <Button leadingIcon={<ArrowLeft className="size-4" />}>
                Back to simulations
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  const terminal = isTerminal(job.status);
  const active = isActive(job.status);
  const artifactsCount = artifacts.data?.items.length ?? 0;
  // Views are a capability: older workers never produce them, and the tab
  // (and its fetches) disappear entirely when the feature is off.
  const viewsEnabled = capabilities.data?.views?.enabled !== false;
  // The molecule is the hero: completed runs open straight onto the built
  // system. Until the user picks a tab, "activity" covers runs in flight.
  const tab: Tab =
    selectedTab ?? (job.status === "completed" && viewsEnabled ? "structure" : "activity");

  return (
    <div>
      <Link
        to="/jobs"
        className="inline-flex items-center gap-1.5 text-[12px] font-medium text-muted transition hover:text-ink"
      >
        <ArrowLeft className="size-3.5" />
        Simulations
      </Link>

      <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={job.status} />
            <Badge tone="neutral">{titleCase(job.input_mode)}</Badge>
            <span className="inline-flex items-center gap-1 rounded-md bg-ink/[0.045] px-1.5 py-0.5 font-mono text-[10.5px] text-muted">
              {job.id.slice(0, 8)}
            </span>
            <CopyButton value={job.id} label="Copy ID" />
          </div>
          <h1 className="mt-2 text-[25px] font-semibold leading-tight tracking-[-0.025em] text-ink">
            {job.name}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
            <span className="inline-flex items-center gap-1">
              <Clock3 className="size-3" />
              created {formatDateTime(job.created_at)}
            </span>
            <span className="inline-flex items-center gap-1">
              <History className="size-3" />
              attempt {job.attempt}
            </span>
            <span
              className={cn(
                "inline-flex items-center gap-1.5",
                connected ? "text-emerald-700" : "text-faint",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  connected ? "animate-soft-pulse bg-emerald-500" : "bg-slate-400",
                )}
              />
              {connected ? "Live stream" : "Polling"}
            </span>
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void jobQuery.refetch()}
            leadingIcon={
              <RefreshCw
                className={cn("size-3.5", jobQuery.isFetching && "animate-spin")}
              />
            }
          >
            Refresh
          </Button>
          {active && job.status !== "canceling" ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCancelOpen(true)}
              leadingIcon={<Ban className="size-3.5 text-rose-500" />}
            >
              Stop
            </Button>
          ) : null}
          {terminal ? (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setRetryOpen(true)}
              leadingIcon={<RotateCcw className="size-3.5" />}
            >
              Retry
            </Button>
          ) : null}
        </div>
      </div>

      {job.error ? (
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-600" />
          <div className="min-w-0">
            <p className="text-[12.5px] font-semibold text-rose-800">
              {titleCase(job.error.code)}
            </p>
            <p className="mt-0.5 text-[12px] leading-relaxed text-rose-700">
              {job.error.message}
            </p>
          </div>
        </div>
      ) : null}

      {job.status === "canceling" ? (
        <div className="mt-4 flex items-center gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-900">
          <Loader2 className="size-4 animate-spin text-amber-600" />
          Stopping gracefully. The latest checkpoint is being preserved.
        </div>
      ) : null}

      {job.status === "queued" ? (
        <div className="mt-4 flex items-center gap-2.5 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-[12.5px] text-violet-900">
          <CircleDot className="size-4 text-violet-600" />
          Queued{job.queue_position ? ` at position ${job.queue_position}` : ""}.
          The GPU worker claims runs oldest first.
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_312px]">
        <div className="min-w-0 space-y-4">
          <ProgressPanel job={job} />

          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-1 border-b border-line px-3 py-2">
              {(
                [
                  ...(viewsEnabled
                    ? [
                        {
                          id: "structure" as const,
                          label: "Structure",
                          icon: Atom,
                        },
                      ]
                    : []),
                  {
                    id: "activity" as const,
                    label: "Activity",
                    icon: Activity,
                    count: events.length,
                  },
                  {
                    id: "artifacts" as const,
                    label: "Artifacts",
                    icon: Database,
                    count: artifactsCount,
                  },
                  { id: "logs" as const, label: "Logs", icon: ScrollText },
                  {
                    id: "configuration" as const,
                    label: "Configuration",
                    icon: FileCode2,
                  },
                  {
                    id: "analysis" as const,
                    label: "Analysis",
                    icon: Thermometer,
                  },
                ]
              ).map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedTab(item.id)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition",
                      tab === item.id
                        ? "bg-brand-50 text-brand-800"
                        : "text-muted hover:bg-ink/[0.04] hover:text-ink",
                    )}
                  >
                    <Icon className="size-3.5" />
                    {item.label}
                    {item.count !== undefined ? (
                      <span
                        className={cn(
                          "rounded-full px-1.5 text-[10px] tabular-nums",
                          tab === item.id
                            ? "bg-brand-100 text-brand-800"
                            : "bg-ink/[0.06] text-faint",
                        )}
                      >
                        {item.count}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>

            {tab === "structure" ? (
              <StructurePanel
                jobId={job.id}
                poll={active}
                maxViewAtoms={capabilities.data?.views?.max_view_atoms}
              />
            ) : null}

            {tab === "activity" ? (
              <div className="px-5 py-4">
                {eventsQuery.isLoading ? (
                  <div className="flex items-center gap-2 text-[12.5px] text-muted">
                    <Spinner /> Loading activity
                  </div>
                ) : (
                  <EventFeed
                    events={events}
                    emptyLabel="No events yet. Activity appears once the worker claims the job."
                  />
                )}
              </div>
            ) : null}

            {tab === "artifacts" ? (
              artifacts.isLoading ? (
                <div className="flex items-center gap-2 px-5 py-8 text-[12.5px] text-muted">
                  <Spinner /> Loading artifacts
                </div>
              ) : (
                <ArtifactTable
                  jobId={job.id}
                  artifacts={artifacts.data?.items ?? []}
                />
              )
            ) : null}

            {tab === "logs" ? <LogViewer jobId={job.id} /> : null}

            {tab === "configuration" ? (
              <ConfigurationPanel jobId={job.id} />
            ) : null}

            {tab === "analysis" ? (
              <AnalysisPanel jobId={job.id} />
            ) : null}
          </Card>
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Stages" description="Worker-reported progress." />
            <div className="px-5 py-4">
              <StageTimeline
                stages={job.stages}
                currentStage={job.current_stage}
              />
            </div>
          </Card>

          <Card>
            <CardHeader title="Details" />
            <div className="divide-y divide-line px-4 py-1">
              <DetailRow label="Status" value={titleCase(job.status)} />
              <DetailRow label="Phase" value={job.phase ?? "—"} />
              <DetailRow label="Input" value={titleCase(job.input_mode)} />
              <DetailRow label="Queue" value={job.queue_position ?? "—"} />
              <DetailRow label="Queued" value={formatDateTime(job.queued_at)} />
              <DetailRow label="Started" value={formatDateTime(job.started_at)} />
              <DetailRow
                label="Completed"
                value={formatDateTime(job.completed_at)}
              />
              <DetailRow label="Job ID" value={job.id} mono />
            </div>
          </Card>

          <div className="rounded-xl bg-ink/[0.035] px-4 py-3">
            <p className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-faint">
              <Terminal className="size-3" />
              Checkpoint safe
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              Stopping sends SIGINT first. The current stage checkpoint is
              written before the worker exits.
            </p>
          </div>
        </aside>
      </div>

      <Modal
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title="Stop this simulation?"
        description="The worker stops gracefully, keeps the latest checkpoint, and any completed artifacts remain downloadable."
        footer={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCancelOpen(false)}
            >
              Keep running
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
            >
              Stop simulation
            </Button>
          </>
        }
      />

      <RetryDialog
        open={retryOpen}
        job={job}
        onClose={() => setRetryOpen(false)}
        onRetried={() => {
          setRetryOpen(false);
          void queryClient.invalidateQueries({ queryKey: ["job", id] });
          void queryClient.invalidateQueries({ queryKey: ["job", id, "events"] });
        }}
      />
    </div>
  );
}

function RetryDialog({
  open,
  job,
  onClose,
  onRetried,
}: {
  open: boolean;
  job: Job;
  onClose: () => void;
  onRetried: () => void;
}) {
  const toast = useToast();
  const completed = job.status === "completed";
  const [mode, setMode] = useState<RetryMode>(completed ? "restart" : "resume");
  const [stage, setStage] = useState(job.current_stage ?? job.stages[0]?.name ?? "");

  const mutation = useMutation({
    mutationFn: (payload: { mode: RetryMode; stage?: string }) =>
      retryJob(job.id, payload.mode, payload.stage),
    onSuccess: () => {
      toast.push({
        tone: "success",
        title: "Retry queued",
        description: "The job is back in the queue with the chosen restart mode.",
      });
      onRetried();
    },
    onError: (error) => {
      const detail =
        error instanceof ApiError && error.details
          ? ` ${JSON.stringify(error.details)}`
          : "";
      toast.push({
        tone: "error",
        title: "Could not retry",
        description:
          error instanceof Error ? `${error.message}${detail}` : "Unknown error",
      });
    },
  });

  const options: Array<{
    value: RetryMode;
    label: string;
    description: string;
    disabled?: boolean;
  }> = [
    {
      value: "resume",
      label: "Resume",
      description: "Continue from the latest checkpoint in the current stage.",
      disabled: completed,
    },
    {
      value: "restart_stage",
      label: "Restart a stage",
      description: "Re-run from a chosen stage and keep earlier results.",
    },
    {
      value: "restart",
      label: "Restart all stages",
      description: "Re-run dynamics from the prepared system.",
    },
    {
      value: "reparameterize",
      label: "Rebuild and restart",
      description: "Re-parameterize the inputs, then start from the first stage.",
    },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Retry this simulation"
      description={
        completed
          ? "A completed run cannot resume. Choose a restart mode to extend or repeat the work."
          : "Pick how much of the existing work to keep."
      }
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={mutation.isPending}
            disabled={mode === "restart_stage" && !stage}
            onClick={() =>
              mutation.mutate({
                mode,
                stage: mode === "restart_stage" ? stage : undefined,
              })
            }
          >
            Queue retry
          </Button>
        </>
      }
    >
      <div className="space-y-2">
        {options.map((option) => {
          const selected = mode === option.value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 transition",
                selected
                  ? "border-brand-300 bg-brand-50/50"
                  : "border-line hover:border-brand-200",
                option.disabled && "cursor-not-allowed opacity-40",
              )}
            >
              <input
                type="radio"
                name="retry-mode"
                value={option.value}
                checked={selected}
                disabled={option.disabled}
                onChange={() => setMode(option.value)}
                className="mt-0.5 accent-brand-600"
              />
              <span>
                <span className="block text-[12.5px] font-medium text-ink">
                  {option.label}
                </span>
                <span className="mt-0.5 block text-[11px] leading-relaxed text-muted">
                  {option.description}
                </span>
              </span>
            </label>
          );
        })}

        {mode === "restart_stage" ? (
          <div className="pt-1">
            <label className="field-label" htmlFor="retry-stage">
              Stage
            </label>
            <Select
              id="retry-stage"
              value={stage}
              onChange={(event) => setStage(event.target.value)}
            >
              {job.stages.map((item) => (
                <option key={item.name} value={item.name}>
                  {humanizeStage(item.name)} · {item.status}
                </option>
              ))}
            </Select>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
