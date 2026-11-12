import {
  useCallback,
  useState,
  useTransition,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  FileBox,
  Layers,
  Loader2,
  Plus,
  Shield,
  Trash2,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createWorkflowVariants,
  deleteWorkflow,
  getWorkflow,
} from "../lib/api";
import {
  useCapabilities,
  useWorkflow,
  useWorkflows,
} from "../lib/queries";
import { useToast } from "../components/ui/Toast";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { Field, TextInput } from "../components/ui/Form";
import { ProgressBar } from "../components/ui/Progress";
import { cn, formatCompact, isActive, isTerminal, statusLabel } from "../lib/utils";
import { StatusBadge } from "../components/ui/Badge";
import type { WorkflowDetailOut, WorkflowJobSummary } from "../lib/types";

export function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId?: string }>();
  const navigate = useNavigate();
  const { push } = useToast();
  const queryClient = useQueryClient();

  const workflow = useWorkflow(workflowId);
  const [isDeleting, setIsDeleting] = useState(false);
  const [variantCount, setVariantCount] = useState(1);
  const [variantName, setVariantName] = useState("");
  const [isCreating, startTransition] = useTransition();

  const w = workflow.data;

  // Every hook must run on every render, so the mutations are declared
  // before the loading and not-found early returns below.
  const deleteMutation = useMutation({
    mutationFn: () => deleteWorkflow(w!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate("/workflows");
      push({ title: "Workflow deleted", description: "Child simulations were left intact.", tone: "info" });
    },
    onError: (cause: unknown) => {
      setIsDeleting(false);
      push({
        title: "Delete failed",
        description: cause instanceof Error ? cause.message : "Could not delete the workflow.",
        tone: "error",
      });
    },
  });

  const variantMutation = useMutation({
    mutationFn: () =>
      createWorkflowVariants(w!.id, {
        count: variantCount,
        name_template: variantName || "{name} · variant {n}",
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["workflow", w!.id] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setVariantCount(1);
      setVariantName("");
      push({
        title: "Variants launched",
        description: `${data.items.length} simulation${data.items.length !== 1 ? "s" : ""} created from "${w!.name}".`,
        tone: "info",
      });
    },
    onError: (cause: unknown) => {
      push({
        title: "Variant launch failed",
        description: cause instanceof Error ? cause.message : "Could not create variant simulations.",
        tone: "error",
      });
    },
  });

  if (workflow.isLoading) {
    return <div className="mx-auto max-w-[760px] px-4 py-6">Loading workflow…</div>;
  }
  if (!w) {
    return (
      <div className="mx-auto max-w-[760px] px-4 py-6">
        <EmptyState
          icon={<Layers className="size-5" />}
          title="Workflow not found"
          description="That workflow does not exist or you do not have access to it."
          action={
            <Button onClick={() => navigate("/workflows")}>
              Browse workflows
            </Button>
          }
        />
      </div>
    );
  }

  const jobs = w.jobs ?? [];
  const activeStatuses = ["queued", "claimed", "running", "canceling"];
  const activeJobs = jobs.filter((j) => activeStatuses.includes(j.status));
  const completedJobs = jobs.filter((j) => j.status === "completed");
  const failedJobs = jobs.filter((j) => j.status === "failed" || j.status === "canceled");

  const handleDelete = () => {
    if (!window.confirm(`Delete workflow "${w.name}"? Child simulations will be kept but unlinked.`)) return;
    setIsDeleting(true);
    deleteMutation.mutate();
  };

  const handleCreateVariant = () => {
    startTransition(() => {
      variantMutation.mutate();
    });
  };

  return (
    <div>
      <PageHeader
        eyebrow="Workflow"
        title={w.name}
        description={
          w.jobs?.length > 0
            ? `${w.jobs.length} derived simulation${w.jobs.length !== 1 ? "s" : ""} from this base system`
            : "No simulations yet. Launch variants from this base system below."
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="danger"
              onClick={handleDelete}
              disabled={isDeleting || deleteMutation.isPending}
              loading={isDeleting || deleteMutation.isPending}
            >
              Delete workflow
            </Button>
            <button
              onClick={() => navigate("/new")}
              className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 text-white shadow-[0_1px_2px_rgba(14,107,98,0.35)] hover:bg-brand-700 px-4 py-2 text-sm font-medium transition"
            >
              <Plus className="size-4" /> New simulation
            </button>
          </div>
        }
      />

      {/* Base system info */}
      <Card className="mb-6 max-w-[760px]">
        <CardHeader title="Base system" description="The structure this workflow was built from" />
        <CardBody className="p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <Layers className="mt-0.5 size-5 text-brand-700" />
              <div>
                <p className="text-[12px] font-medium text-ink">Source file</p>
                <p className="text-[11px] text-faint">
                  {w.source_file_id} · {w.source_type}
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Shield className="mt-0.5 size-5 text-brand-700" />
              <div>
                <p className="text-[12px] font-medium text-ink">Workflow ID</p>
                <p className="text-[11px] text-faint truncate">{w.id}</p>
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Variant creation */}
      <Card>
        <CardHeader
          title="Launch variants"
          description="Create multiple simulations from this base system, all sharing the same input structure."
        />
        <CardBody className="p-6">
          <form onSubmit={(e) => { e.preventDefault(); handleCreateVariant(); }} className="space-y-4">
            <Field
              label="Number of variants"
              htmlFor="variant-count"
              hint="How many simulation jobs to launch from this base system"
            >
              <TextInput
                id="variant-count"
                type="number"
                min="1"
                max="50"
                value={variantCount}
                onChange={(e) => setVariantCount(Math.max(1, Math.min(50, parseInt(e.target.value) || 1)))}
                disabled={isCreating || variantMutation.isPending}
                className="w-[80px]"
              />
            </Field>
            <Field
              label="Name template"
              htmlFor="variant-name"
              hint="Use {name} for the workflow name and {n} for the variant number"
            >
              <TextInput
                id="variant-name"
                value={variantName}
                onChange={(e) => setVariantName(e.target.value)}
                placeholder="{name} · variant {n}"
                disabled={isCreating || variantMutation.isPending}
              />
            </Field>
            <div className="pt-4 flex justify-end">
              <Button
                type="submit"
                variant="primary"
                disabled={isCreating || variantMutation.isPending}
                loading={isCreating || variantMutation.isPending}
              >
                {isCreating || variantMutation.isPending ? "Launching…" : "Launch variants"}
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>

      {/* Child jobs */}
      {jobs.length > 0 && (
        <Card className="mt-6 overflow-hidden">
          <CardHeader
            title="Derived simulations"
            description={`${jobs.length} simulation${jobs.length !== 1 ? "s" : ""} launched from this base system`}
          />
          <CardBody className="p-0">
            <div className="divide-y divide-line">
              {jobs.map((job) => (
                <WorkflowJobRow key={job.id} job={job} />
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {workflow.isError ? (
        <p className="mt-3 text-[12px] text-rose-600">
          {workflow.error instanceof Error
            ? workflow.error.message
            : "Could not refresh workflow."}
        </p>
      ) : null}
    </div>
  );
}

function WorkflowJobRow({ job }: { job: WorkflowJobSummary }) {
  const navigate = useNavigate();
  const percent = (job.progress?.percent ?? 0);

  return (
    <div
      onClick={() => navigate(`/jobs/${job.id}`)}
      className="group grid grid-cols-[minmax(0,1fr)_auto_auto_92px_20px] items-center gap-x-4 gap-y-2 px-5 py-3.5 transition hover:bg-surface-muted cursor-pointer sm:grid-cols-[minmax(0,2.1fr)_minmax(0,1.15fr)_130px_92px_20px]"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") navigate(`/jobs/${job.id}`);
      }}
    >
      <div className="min-w-0">
        <p className="truncate text-[13.5px] font-medium text-ink group-hover:text-brand-800">
          {job.name}
        </p>
        <p className="mt-0.5 truncate text-[11px] text-faint">
          {job.status === "queued"
            ? `Queue position ${"—"}`
            : job.phase ?? statusLabel(job.status)}
        </p>
      </div>
      <StatusBadge status={job.status} />
      <span className="text-[11px] text-faint tabular-nums">
        {percent}%
      </span>
      <span className="text-[11px] text-faint">
        {job.created_at}
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          navigate(`/jobs/${job.id}`);
        }}
        className="rounded-md p-1.5 text-faint transition hover:bg-ink/5 hover:text-ink"
        aria-label="View job"
      >
        <ArrowRight className="size-3.5" />
      </button>
    </div>
  );
}
