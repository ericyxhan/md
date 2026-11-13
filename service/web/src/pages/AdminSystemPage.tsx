import {
  Cpu,
  HardDrive,
  RefreshCw,
} from "lucide-react";
import { useAdminSystem } from "../lib/queries";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import {
  formatBytes,
  formatCompact,
  cn,
} from "../lib/utils";

const QUEUE_ORDER = [
  "queued",
  "claimed",
  "running",
  "canceling",
  "failed",
  "completed",
  "canceled",
];


function secondsToHuman(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function StatRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "good" | "bad" | "muted";
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line py-2.5 last:border-0">
      <span className="text-[12px] text-muted">{label}</span>
      <span
        className={cn(
          "text-[12.5px] font-medium tabular-nums",
          tone === "good" && "text-emerald-700",
          tone === "bad" && "text-rose-600",
          tone !== "good" && tone !== "bad" && "text-ink",
        )}
      >
        {value}
      </span>
    </div>
  );
}

/** System health: what the readyz check verifies, plus the business state. */
export function AdminSystemPage() {
  const system = useAdminSystem();

  const healthy =
    system.data?.database.reachable === true &&
    (system.data?.workers.length ?? 0) > 0 &&
    (system.data?.workers ?? []).every((worker) => !worker.stale);

  return (
    <div>
      <PageHeader
        eyebrow="Administration"
        title="System health"
        description="What the service checks itself with, plus how much it is holding — database, disk, queue, and whether the worker is still heartbeating."
        actions={
          <Button
            variant="secondary"
            size="sm"
            leadingIcon={<RefreshCw className={system.isFetching ? "size-3.5 animate-spin" : "size-3.5"} />}
            onClick={() => void system.refetch()}
          >
            Refresh
          </Button>
        }
      />

      {system.isError ? (
        <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-[13px] text-rose-700">
          {system.error instanceof Error
            ? system.error.message
            : "Could not load system health."}
        </p>
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader
            title="Service"
            description="What /readyz checks: the database answers, the schema is migrated, and the data root is writable."
            action={
              healthy ? (
                <Badge tone="green" dot>
                  Healthy
                </Badge>
              ) : (
                <Badge tone="amber" dot>
                  Needs attention
                </Badge>
              )
            }
          />
          <div className="px-5 py-4">
            <StatRow label="API version" value={system.data?.api_version ?? "…"} />
            <StatRow
              label="Database reachable"
              value={system.data?.database.reachable ? "Yes" : "No"}
              tone={system.data?.database.reachable ? "good" : "bad"}
            />
            <StatRow
              label="Migration"
              value={system.data?.database.migration ?? "unknown"}
            />
            <StatRow label="Audit events" value={system.data?.database.audit_events ?? "…"} />
            <StatRow label="Artifacts" value={formatCompact(system.data?.database.artifacts ?? 0)} />
            <StatRow
              label="Artifact bytes"
              value={formatBytes(system.data?.database.artifact_bytes ?? 0)}
            />
          </div>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader
            title="Data"
            description="What the deployment is holding and how much room is left on the disk."
            action={<HardDrive className="size-4 text-faint" />}
          />
          <div className="px-5 py-4">
            <StatRow
              label="Free space"
              value={`${formatBytes(system.data?.data_root.free_bytes ?? 0)} (min. ${formatBytes(system.data?.data_root.min_free_bytes ?? 0)})`}
              tone={
                (system.data?.data_root.free_bytes ?? 0) >
                (system.data?.data_root.min_free_bytes ?? 0)
                  ? "good"
                  : "bad"
              }
            />
            <StatRow
              label="Account data"
              value={formatBytes(system.data?.data_root.users_bytes ?? 0)}
            />
            <StatRow label="Data root" value={system.data?.data_root.path ?? "…"} />
            <div className="mt-4 flex flex-wrap items-center gap-1.5">
              {QUEUE_ORDER.map((status) => (
                <Badge
                  key={status}
                  tone={
                    status === "failed" || status === "canceling"
                      ? "rose"
                      : status === "queued" || status === "claimed" || status === "running"
                        ? "amber"
                        : "neutral"
                  }
                  dot
                >
                  {status} {system.data?.queue_counts[status] ?? 0}
                </Badge>
              ))}
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden lg:col-span-2">
          <CardHeader
            title="Workers"
            description="The GPU worker heartbeats. A stale heartbeat means a job could be orphaned mid-run; the reaper handles lease expiry, but a long silence deserves a look."
            action={<Cpu className="size-4 text-faint" />}
          />
          {system.isLoading ? (
            <div className="px-5 py-6 text-[12.5px] text-muted">Loading worker state…</div>
          ) : (system.data?.workers.length ?? 0) === 0 ? (
            <p className="px-5 py-6 text-[12.5px] text-muted">No workers have registered.</p>
          ) : (
            <div className="divide-y divide-line">
              {system.data?.workers.map((worker) => (
                <div
                  key={worker.id}
                  className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4"
                >
                  <div className="flex w-40 shrink-0 flex-col">
                    <span className="text-[13px] font-semibold text-ink">
                      {worker.id}
                    </span>
                    <span className="text-[10.5px] text-faint">{worker.hostname}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-muted">GPU</span>
                    <span className="text-[12.5px] font-medium text-ink">
                      {worker.gpu_name || "not reported"}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-muted">Version</span>
                    <span className="text-[12.5px] font-medium text-ink">
                      {worker.version || "—"}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-muted">Status</span>
                    <span className="text-[12.5px] font-medium text-ink">
                      {worker.status}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-muted">Heartbeat</span>
                    <span
                      className={cn(
                        "text-[12.5px] font-medium",
                        worker.stale ? "text-rose-600" : "text-ink",
                      )}
                    >
                      {secondsToHuman(worker.heartbeat_age_seconds)}
                    </span>
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="text-[11px] text-muted">Current job</span>
                    <span className="truncate text-[11.5px] text-faint">
                      {worker.current_job_id ?? "idle"}
                    </span>
                  </div>
                  <div className="shrink-0">
                    {worker.stale ? (
                      <Badge tone="rose" dot>
                        Stale
                      </Badge>
                    ) : worker.current_job_id ? (
                      <Badge tone="amber" dot>
                        Busy
                      </Badge>
                    ) : (
                      <Badge tone="green" dot>
                        Idle
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
