import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ExternalLink,
  Gauge,
  PauseCircle,
} from "lucide-react";
import {
  useAdminJobs,
  useAdminSystem,
  type AdminJobFilter,
} from "../lib/queries";
import { PageHeader } from "../components/layout/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { Badge } from "../components/ui/Badge";
import { StatusBadge } from "../components/ui/Badge";
import { formatRelative, cn } from "../lib/utils";
import type { AdminJob } from "../lib/types";

const FILTERS: Array<{ id: AdminJobFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "queued", label: "Queued" },
  { id: "running", label: "Running" },
  { id: "failed", label: "Failed" },
];

function JobRow({ job }: { job: AdminJob }) {
  const active = job.status === "queued" || job.status === "claimed" || job.status === "running" || job.status === "canceling";
  const ownerName = `${job.owner_first_name} ${job.owner_last_name}`.trim();
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 transition hover:bg-surface-muted"
    >
      <div className="min-w-0 flex-[1.6]">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-medium text-ink group-hover:text-brand-800">
            {job.name}
          </span>
          {job.stale ? (
            <Badge tone="rose" dot>
              Stuck
            </Badge>
          ) : null}
        </div>
        <p className="mt-0.5 truncate text-[11px] text-faint">
          {ownerName} · {job.owner_email}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <StatusBadge status={job.status} />
        {job.phase && job.phase !== job.status ? (
          <span className="hidden text-[11px] text-faint sm:inline">{job.phase}</span>
        ) : null}
      </div>

      <div className="flex w-24 shrink-0 flex-col items-end gap-0.5">
        <span className="text-[11px] text-muted">attempt {job.attempt}</span>
        <span className="text-[10px] text-faint">{formatRelative(job.created_at)}</span>
      </div>

      <ExternalLink className="size-3.5 shrink-0 text-faint transition group-hover:text-brand-700" />
    </Link>
  );
}

/**
 * Cross-account queue view.  Jobs are normally listed per account; this
 * page shows the whole platform so the administrator can see who is
 * waiting, what is running, and which jobs are going nowhere.
 */
export function AdminJobsPage() {
  const [filter, setFilter] = useState<AdminJobFilter>("all");
  const jobs = useAdminJobs(filter);
  const system = useAdminSystem();

  const items = jobs.data?.items ?? [];
  const counts = system.data?.queue_counts ?? {};

  const badgeFor = (id: AdminJobFilter) => {
    if (id === "all") return system.data?.database.jobs ?? "…";
    return counts[id] ?? 0;
  };

  const failing = useMemo(
    () => items.filter((job) => job.status === "failed").length,
    [items],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Administration"
        title="Platform queue"
        description="Every job on this deployment across every account — what is waiting, what is running, and what is not going anywhere."
        actions={
          <Link
            to="/admin/system"
            className="inline-flex items-center gap-1.5 text-[12px] font-medium text-brand-700 transition hover:text-brand-800"
          >
            <Gauge className="size-3.5" />
            System health
          </Link>
        }
      />

      <Card className="mt-6 overflow-hidden">
        <CardHeader
          title="All jobs"
          description={`${items.length} loaded · newest first`}
          action={
            <div className="flex items-center gap-1">
              {FILTERS.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setFilter(entry.id)}
                  className={cn(
                    "rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition",
                    filter === entry.id
                      ? "bg-brand-50 text-brand-800"
                      : "text-muted hover:bg-ink/5 hover:text-ink",
                  )}
                >
                  {entry.label}
                  <span className="ml-1.5 tabular-nums text-[10.5px] text-faint">
                    {badgeFor(entry.id)}
                  </span>
                </button>
              ))}
            </div>
          }
        />

        {jobs.isLoading ? (
          <div className="divide-y divide-line">
            {[0, 1, 2].map((item) => (
              <div key={item} className="animate-pulse px-5 py-4">
                <div className="h-3 w-48 rounded bg-line" />
                <div className="mt-2 h-2.5 w-64 rounded bg-line" />
              </div>
            ))}
          </div>
        ) : jobs.isError ? (
          <div className="px-5 py-8 text-center">
            <p className="text-[13px] font-medium text-rose-600">
              {jobs.error instanceof Error ? jobs.error.message : "Could not load the platform queue."}
            </p>
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<PauseCircle className="size-5" />}
            title="Nothing matches this filter"
            description={
              filter === "all"
                ? "No jobs exist on this deployment yet."
                : `No ${filter} jobs right now.`
            }
          />
        ) : (
          <div className="divide-y divide-line">
            {items.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[11px] text-faint">
          <span className="inline-flex items-center gap-1.5">
            <Activity className="size-3" />
            Auto-refreshing every 10 seconds
          </span>
          {failing > 0 ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-rose-600">
              <AlertTriangle className="size-3" />
              {failing} failing in this window
            </span>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
