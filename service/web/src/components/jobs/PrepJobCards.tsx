import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { PrepJobStatus } from "../../lib/types";
import { formatRelative } from "../../lib/utils";
import { StatusBadge } from "../ui/Badge";
import { ProgressBar } from "../ui/Progress";

/**
 * A table of system-preparation jobs, mirroring the simulations table so
 * the two workspaces read the same way: history first, one row per job, with
 * live progress for anything still running.
 */
export function PrepJobRow({ job }: { job: PrepJobStatus }) {
  const navigate = useNavigate();
  const base =
    job.type === "membrane_embed" ? "/prep/membrane" : "/prep/system-prep";
  const active =
    job.status === "queued" ||
    job.status === "claimed" ||
    job.status === "running";
  const percent = job.progress_percent;

  return (
    <button
      type="button"
      onClick={() => navigate(`${base}/${job.id}`)}
      className="group grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-3.5 text-left transition hover:bg-surface-muted sm:grid-cols-[minmax(0,2.1fr)_minmax(0,1.15fr)_130px_92px_20px]"
    >
      <div className="min-w-0">
        <p className="truncate text-[13.5px] font-medium text-ink group-hover:text-brand-800">
          {job.label || job.type}
        </p>
        <p className="mt-0.5 truncate text-[11px] text-faint">
          {job.progress_message ??
            job.error ??
            job.phase ??
            `queued ${formatRelative(job.created_at)}`}
        </p>
      </div>

      <div className="min-w-0">
        {active && percent != null ? (
          <div className="flex items-center gap-2">
            <ProgressBar value={percent} className="h-1.5 flex-1" animated />
            <span className="shrink-0 text-[11px] tabular-nums text-muted">
              {Math.round(percent)}%
            </span>
          </div>
        ) : job.output_file_ids.length > 0 ? (
          <span className="text-[11px] text-muted">
            {job.output_file_ids.length} output
            {job.output_file_ids.length !== 1 ? "s" : ""}
          </span>
        ) : (
          <span className="text-[11px] text-faint">—</span>
        )}
      </div>

      <StatusBadge status={job.status} className="justify-self-start" />

      <span className="text-[11px] text-faint">
        {formatRelative(job.created_at)}
      </span>

      <ChevronRight className="size-3.5 shrink-0 text-faint transition group-hover:text-brand-600" />
    </button>
  );
}
