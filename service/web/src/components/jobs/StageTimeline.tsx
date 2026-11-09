import {
  CheckCircle2,
  Circle,
  CircleDashed,
  Loader2,
  MinusCircle,
  XCircle,
} from "lucide-react";
import type { StageOut, StageStatus } from "../../lib/types";
import {
  cn,
  formatCompact,
  humanizeStage,
  stageProgress,
  statusLabel,
} from "../../lib/utils";

function StageIcon({ status }: { status: StageStatus }) {
  const base = "size-4 shrink-0";
  switch (status) {
    case "completed":
      return <CheckCircle2 className={cn(base, "text-emerald-600")} />;
    case "running":
      return <Loader2 className={cn(base, "animate-spin text-sky-600")} />;
    case "failed":
      return <XCircle className={cn(base, "text-rose-600")} />;
    case "skipped":
      return <MinusCircle className={cn(base, "text-slate-400")} />;
    case "canceled":
      return <CircleDashed className={cn(base, "text-slate-400")} />;
    case "pending":
      return <CircleDashed className={cn(base, "text-slate-300")} />;
    default:
      return <Circle className={cn(base, "text-slate-300")} />;
  }
}

export function StageTimeline({
  stages,
  currentStage,
  compact = false,
  className,
}: {
  stages: StageOut[];
  currentStage?: string | null;
  compact?: boolean;
  className?: string;
}) {
  if (stages.length === 0) {
    return (
      <p className="text-[13px] text-muted">Stages appear when the job starts.</p>
    );
  }

  return (
    <ol className={cn("relative", className)}>
      {stages.map((stage, index) => {
        const isLast = index === stages.length - 1;
        const active =
          stage.status === "running" ||
          (stage.status === "pending" && stage.name === currentStage);
        const percent = stageProgress(
          stage.steps_completed,
          stage.steps_target,
        );
        return (
          <li
            key={stage.name}
            className={cn("relative flex gap-3", isLast ? "pb-0" : "pb-4")}
          >
            {!isLast ? (
              <span
                className={cn(
                  "absolute left-[7.5px] top-5 h-[calc(100%-12px)] w-px",
                  stage.status === "completed"
                    ? "bg-emerald-200"
                    : "bg-line",
                )}
              />
            ) : null}
            <span className="relative z-10 mt-0.5 flex size-4 items-center justify-center bg-surface">
              <StageIcon status={stage.status} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <p
                  className={cn(
                    "truncate text-[13px] font-medium",
                    active ? "text-ink" : "text-ink-soft",
                  )}
                >
                  {stage.kind === "minimization"
                    ? "Energy minimization"
                    : humanizeStage(stage.name)}
                  {stage.attempts > 1 ? (
                    <span className="ml-1.5 text-[10.5px] font-normal text-faint">
                      attempt {stage.attempts}
                    </span>
                  ) : null}
                </p>
                <span
                  className={cn(
                    "shrink-0 text-[11px] font-medium",
                    stage.status === "completed"
                      ? "text-emerald-700"
                      : stage.status === "running"
                        ? "text-sky-700"
                        : stage.status === "failed"
                          ? "text-rose-700"
                          : "text-faint",
                  )}
                >
                  {statusLabel(stage.status)}
                </span>
              </div>

              {stage.kind !== "minimization" ? (
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-line">
                    <div
                      className={cn(
                        "h-full rounded-full transition-[width] duration-700",
                        stage.status === "completed"
                          ? "bg-emerald-500"
                          : stage.status === "failed"
                            ? "bg-rose-500"
                            : "bg-sky-500",
                      )}
                      style={{
                        width: `${stage.status === "completed" ? 100 : percent}%`,
                      }}
                    />
                  </div>
                  {!compact ? (
                    <span className="w-24 shrink-0 text-right text-[10.5px] tabular-nums text-faint">
                      {formatCompact(stage.steps_completed)} /{" "}
                      {formatCompact(stage.steps_target)}
                    </span>
                  ) : null}
                </div>
              ) : null}

              {stage.error ? (
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-rose-600">
                  {stage.error}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
