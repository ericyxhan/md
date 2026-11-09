import { useState } from "react";
import {
  Archive,
  Download,
  FileBox,
  FileText,
  Film,
  Save,
} from "lucide-react";
import type { Artifact } from "../../lib/types";
import { downloadArtifact } from "../../lib/api";
import { cn, formatBytes, formatDateTime, titleCase } from "../../lib/utils";
import { EmptyState } from "../ui/EmptyState";

function artifactIcon(kind: string) {
  switch (kind) {
    case "trajectory":
      return Film;
    case "checkpoint":
      return Save;
    case "structure":
      return FileBox;
    case "log":
      return FileText;
    default:
      return Archive;
  }
}

const kindTone: Record<string, string> = {
  trajectory: "bg-violet-50 text-violet-700",
  checkpoint: "bg-amber-50 text-amber-700",
  structure: "bg-sky-50 text-sky-700",
  log: "bg-slate-100 text-slate-600",
  metadata: "bg-brand-50 text-brand-700",
};

export function ArtifactTable({
  jobId,
  artifacts,
}: {
  jobId: string;
  artifacts: Artifact[];
}) {
  const [filter, setFilter] = useState("all");
  const kinds = Array.from(new Set(artifacts.map((item) => item.kind))).sort();
  const visible =
    filter === "all"
      ? artifacts
      : artifacts.filter((item) => item.kind === filter);

  if (artifacts.length === 0) {
    return (
      <EmptyState
        icon={<Archive className="size-5" />}
        title="No artifacts yet"
        description="Trajectories, checkpoints, and final structures appear here when the worker reports completion."
      />
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-5 py-2.5">
        <button
          type="button"
          onClick={() => setFilter("all")}
          className={cn(
            "rounded-full px-2.5 py-1 text-[11.5px] font-medium transition",
            filter === "all"
              ? "bg-ink text-white"
              : "text-muted hover:bg-ink/5 hover:text-ink",
          )}
        >
          All · {artifacts.length}
        </button>
        {kinds.map((kind) => {
          const count = artifacts.filter((item) => item.kind === kind).length;
          return (
            <button
              key={kind}
              type="button"
              onClick={() => setFilter(kind)}
              className={cn(
                "rounded-full px-2.5 py-1 text-[11.5px] font-medium transition",
                filter === kind
                  ? "bg-ink text-white"
                  : "text-muted hover:bg-ink/5 hover:text-ink",
              )}
            >
              {titleCase(kind)} · {count}
            </button>
          );
        })}
      </div>

      <div className="divide-y divide-line">
        {visible.map((artifact) => {
          const Icon = artifactIcon(artifact.kind);
          return (
            <div
              key={artifact.id}
              className="flex items-center gap-3 px-5 py-3 transition hover:bg-surface-muted"
            >
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-lg",
                  kindTone[artifact.kind] ?? "bg-slate-100 text-slate-600",
                )}
              >
                <Icon className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink">
                  {artifact.name}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-faint">
                  {titleCase(artifact.kind)}
                  {artifact.stage_name
                    ? ` · ${titleCase(artifact.stage_name)}`
                    : ""}{" "}
                  · {formatBytes(artifact.size_bytes)} ·{" "}
                  {formatDateTime(artifact.created_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => downloadArtifact(jobId, artifact)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-[12px] font-medium text-ink-soft transition hover:border-brand-300 hover:text-brand-800"
              >
                <Download className="size-3.5" />
                <span className="hidden sm:inline">Download</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
