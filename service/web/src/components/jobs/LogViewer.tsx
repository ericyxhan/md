import { useState } from "react";
import { Download, FileText, RefreshCw } from "lucide-react";
import type { LogEntry } from "../../lib/types";
import { logDownloadUrl } from "../../lib/api";
import { useLogTail, useLogs } from "../../lib/queries";
import { cn, formatBytes, formatDateTime } from "../../lib/utils";
import { EmptyState, Spinner } from "../ui/EmptyState";
import { CopyButton } from "../ui/CopyButton";

export function LogViewer({ jobId }: { jobId: string }) {
  const logs = useLogs(jobId);
  const [selected, setSelected] = useState<string | null>(null);
  const entries = logs.data?.items ?? [];
  const active =
    entries.find((entry) => entry.relative_path === selected) ?? entries[0];
  const tail = useLogTail(jobId, active?.relative_path, Boolean(active));

  if (logs.isLoading) {
    return (
      <div className="flex items-center gap-2 px-5 py-8 text-[13px] text-muted">
        <Spinner /> Loading logs
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={<FileText className="size-5" />}
        title="No logs available"
        description="Worker stdout, stderr, and simulation logs appear here while a job runs."
      />
    );
  }

  return (
    <div className="grid min-h-[340px] sm:grid-cols-[190px_minmax(0,1fr)]">
      <div className="border-b border-line sm:border-b-0 sm:border-r">
        <div className="px-3 py-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">
          Log files
        </div>
        <div className="space-y-0.5 px-2 pb-2">
          {entries.map((entry: LogEntry) => (
            <button
              key={entry.relative_path}
              type="button"
              onClick={() => setSelected(entry.relative_path)}
              className={cn(
                "w-full rounded-lg px-2.5 py-2 text-left transition",
                active?.relative_path === entry.relative_path
                  ? "bg-brand-50 text-brand-800"
                  : "text-ink-soft hover:bg-ink/[0.04]",
              )}
            >
              <p className="truncate text-[12px] font-medium">{entry.name}</p>
              <p className="mt-0.5 text-[10.5px] text-faint">
                {formatBytes(entry.size_bytes)}
              </p>
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-w-0 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2">
          <div className="min-w-0">
            <p className="truncate text-[12px] font-medium text-ink">
              {active?.relative_path}
            </p>
            {active ? (
              <p className="text-[10.5px] text-faint">
                updated {formatDateTime(active.updated_at)}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => void tail.refetch()}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11.5px] font-medium text-muted transition hover:bg-ink/5 hover:text-ink"
            >
              <RefreshCw
                className={cn("size-3", tail.isFetching && "animate-spin")}
              />
              Refresh
            </button>
            {active ? (
              <>
                <CopyButton value={tail.data?.content ?? ""} label="Copy" />
                <a
                  href={logDownloadUrl(jobId, active)}
                  className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11.5px] font-medium text-muted transition hover:bg-ink/5 hover:text-ink"
                >
                  <Download className="size-3" />
                  Download
                </a>
              </>
            ) : null}
          </div>
        </div>

        <div className="relative min-h-0 flex-1 bg-[#0d1b24] p-4">
          {tail.isLoading ? (
            <div className="flex items-center gap-2 text-[12px] text-slate-400">
              <Spinner /> Reading log
            </div>
          ) : tail.data?.content ? (
            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words font-mono text-[11.5px] leading-relaxed text-slate-200">
              {tail.data.content}
            </pre>
          ) : (
            <p className="text-[12px] text-slate-400">
              This log is empty right now.
            </p>
          )}
          {tail.data?.truncated ? (
            <p className="mt-3 border-t border-white/10 pt-2 text-[10.5px] text-slate-400">
              Showing the last {tail.data.lines} lines. Download the file for the
              complete log.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
