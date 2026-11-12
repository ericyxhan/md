import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Layers,
  Plus,
  Search,
} from "lucide-react";
import type { WorkflowOut } from "../lib/types";
import { useWorkflows } from "../lib/queries";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { TextInput } from "../components/ui/Form";
import { cn } from "../lib/utils";
import { Badge } from "../components/ui/Badge";
export function WorkflowsPage() {
  const workflows = useWorkflows();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const items = workflows.data ?? [];

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return items.filter((workflow) => {
      if (!term) return true;
      return (
        workflow.name.toLowerCase().includes(term) ||
        workflow.id.toLowerCase().includes(term) ||
        workflow.source_type.toLowerCase().includes(term)
      );
    });
  }, [items, query]);

  const totalJobs = useMemo(
    () => items.reduce((sum, w) => sum + w.job_count, 0),
    [items],
  );

  const activeJobs = useMemo(
    () =>
      items.reduce((sum, w) => {
        // We don't have per-job status in the list view, so estimate from count
        return sum;
      }, 0),
    [items],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Workflows"
        description={
          totalJobs > 0
            ? `${items.length} workflow · ${totalJobs} derived simulation${totalJobs !== 1 ? "s" : ""}`
            : "No workflows yet. Create one from a completed system preparation or membrane embedding job."
        }
        actions={
          <Button
            variant="primary"
            leadingIcon={<Plus className="size-4" />}
            onClick={() => navigate("/new")}
          >
            New simulation
          </Button>
        }
      />

      <Card className="mt-6 overflow-hidden">
        <CardHeader
          title="All workflows"
          description={`${items.length} workflow${items.length !== 1 ? "s" : ""} · ${totalJobs} derived simulation${totalJobs !== 1 ? "s" : ""}`}
          action={
            <div className="relative w-56">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
              <TextInput
                className="h-8 pl-8 text-[12px]"
                placeholder="Search workflows"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search workflows"
              />
            </div>
          }
        />

        {workflows.isLoading ? (
          <div className="divide-y divide-line">
            {[0, 1, 2, 3].map((item) => (
              <div key={item} className="animate-pulse px-5 py-4">
                <div className="h-3 w-48 rounded bg-line" />
                <div className="mt-2 h-2.5 w-32 rounded bg-line" />
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            icon={<Layers className="size-5" />}
            title={
              items.length === 0
                ? "No workflows yet"
                : "No workflows match this view"
            }
            description={
              items.length === 0
                ? "Run a system preparation or membrane embedding, then save its output as a workflow base system to launch related simulations from it."
                : "Try a different search term."
            }
            action={
              items.length === 0 ? (
                <Button
                  variant="secondary"
                  onClick={() => navigate("/new")}
                >
                  Start a simulation
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => setQuery("")}
                >
                  Clear search
                </Button>
              )
            }
          />
        ) : (
          <div className="divide-y divide-line">
            {visible.map((workflow) => (
              <WorkflowRow key={workflow.id} workflow={workflow} />
            ))}
          </div>
        )}
      </Card>

      {workflows.isError ? (
        <p className="mt-3 text-[12px] text-rose-600">
          {workflows.error instanceof Error
            ? workflows.error.message
            : "Could not refresh workflows."}
        </p>
      ) : null}
    </div>
  );
}

function WorkflowRow({ workflow }: { workflow: WorkflowOut }) {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => navigate(`/workflows/${workflow.id}`)}
      className="group grid grid-cols-[minmax(0,1fr)_auto_auto_92px_20px] items-center gap-x-4 gap-y-2 px-5 py-4 transition hover:bg-surface-muted cursor-pointer sm:grid-cols-[minmax(0,2.1fr)_minmax(0,1.15fr)_130px_92px_20px]"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") navigate(`/workflows/${workflow.id}`);
      }}
    >
      <div className="min-w-0">
        <p className="truncate text-[13.5px] font-medium text-ink group-hover:text-brand-800">
          {workflow.name}
        </p>
        <p className="mt-0.5 truncate text-[11px] text-faint">
          {workflow.job_count} derived simulation{workflow.job_count !== 1 ? "s" : ""} · {workflow.source_type}
        </p>
      </div>
      <Badge
        tone={workflow.job_count > 0 ? "brand" : "neutral"}
        dot={workflow.job_count > 0}
      >
        {workflow.job_count} job{workflow.job_count !== 1 ? "s" : ""}
      </Badge>
      <span className="text-[11px] text-faint tabular-nums">{workflow.job_count}</span>
      <span className="text-[11px] text-faint">
        {new Date(workflow.created_at).toLocaleDateString()}
      </span>
    </div>
  );
}
