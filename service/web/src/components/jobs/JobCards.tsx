import { Link } from "react-router-dom";
import { ChevronRight, Clock3 } from "lucide-react";
import type { Job } from "../../lib/types";
import {
  formatCompact,
  formatRelative,
  humanizeStage,
  isActive,
  jobPercent,
} from "../../lib/utils";
import { StatusBadge } from "../ui/Badge";
import { ProgressBar, ProgressRing } from "../ui/Progress";

export function ActiveJobCard({ job }: { job: Job }) {
  const percent = jobPercent(job);
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="group card block p-4 transition duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-[var(--shadow-float)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-semibold text-ink group-hover:text-brand-800">
            {job.name}
          </p>
          <p className="mt-0.5 text-[11.5px] text-muted">
            {job.current_stage
              ? humanizeStage(job.current_stage)
              : job.status === "queued"
                ? `Queue position ${job.queue_position ?? "—"}`
                : "Preparing worker"}
          </p>
        </div>
        <StatusBadge status={job.status} />
      </div>

      <div className="mt-4 flex items-center gap-4">
        <ProgressRing
          value={percent}
          size={52}
          stroke={5}
          tone={job.status === "failed" ? "rose" : "brand"}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2 text-[11px]">
            <span className="text-muted">Overall progress</span>
            <span className="mono text-[11px] text-ink-soft">
              {job.progress?.step != null
                ? `${formatCompact(job.progress.step)} / ${formatCompact(job.progress.total_steps)}`
                : "Waiting"}
            </span>
          </div>
          <ProgressBar
            value={percent}
            className="mt-1.5"
            tone={job.status === "failed" ? "rose" : "brand"}
            animated={isActive(job.status)}
          />
          <div className="mt-2 flex items-center gap-1.5 text-[10.5px] text-faint">
            <Clock3 className="size-3" />
            updated {formatRelative(job.updated_at)}
          </div>
        </div>
      </div>
    </Link>
  );
}

export function JobRow({ job }: { job: Job }) {
  const percent = jobPercent(job);
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-3.5 transition hover:bg-surface-muted sm:grid-cols-[minmax(0,2.1fr)_minmax(0,1.15fr)_130px_92px_20px]"
    >
      <div className="min-w-0">
        <p className="truncate text-[13.5px] font-medium text-ink group-hover:text-brand-800">
          {job.name}
        </p>
        <p className="mt-0.5 truncate text-[11px] text-faint">
          {job.input_mode === "pdb_id"
            ? "PDB download"
            : job.input_mode === "complex"
              ? "Protein–ligand complex"
              : "Protein + ligands"}{" "}
          · {job.id.slice(0, 8)}
        </p>
      </div>

      <div className="hidden min-w-0 sm:block">
        <p className="truncate text-[12.5px] text-ink-soft">
          {job.current_stage
            ? humanizeStage(job.current_stage)
            : job.status === "queued"
              ? `Queued · #${job.queue_position ?? "—"}`
              : "—"}
        </p>
        <p className="mt-0.5 text-[10.5px] text-faint">
          {job.stages.length} stage{job.stages.length === 1 ? "" : "s"}
        </p>
      </div>

      <div className="hidden items-center gap-2 sm:flex">
        <div className="w-[70px]">
          <ProgressBar
            value={percent}
            tone={
              job.status === "failed"
                ? "rose"
                : job.status === "completed"
                  ? "green"
                  : "brand"
            }
          />
        </div>
        <span className="mono w-9 text-right text-[10.5px] text-muted">
          {Math.round(percent)}%
        </span>
      </div>

      <div className="flex justify-end sm:justify-start">
        <StatusBadge status={job.status} />
      </div>

      <div className="hidden text-right text-[11px] text-faint sm:block">
        {formatRelative(job.created_at)}
      </div>

      <ChevronRight className="hidden size-4 text-faint transition group-hover:translate-x-0.5 group-hover:text-brand-600 sm:block" />
    </Link>
  );
}
