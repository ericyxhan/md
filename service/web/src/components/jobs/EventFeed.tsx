import {
  Activity,
  AlertCircle,
  CheckCircle2,
  FileDown,
  Layers,
  Sparkles,
} from "lucide-react";
import type { JobEvent } from "../../lib/types";
import { cn, formatDateTime, titleCase } from "../../lib/utils";

function eventIcon(type: string) {
  switch (type) {
    case "error":
    case "failed":
      return { Icon: AlertCircle, className: "text-rose-600 bg-rose-50" };
    case "completed":
      return {
        Icon: CheckCircle2,
        className: "text-emerald-600 bg-emerald-50",
      };
    case "stage":
      return { Icon: Layers, className: "text-sky-600 bg-sky-50" };
    case "artifact":
      return { Icon: FileDown, className: "text-violet-600 bg-violet-50" };
    case "progress":
      return { Icon: Activity, className: "text-brand-600 bg-brand-50" };
    default:
      return { Icon: Sparkles, className: "text-slate-500 bg-slate-100" };
  }
}

export function EventFeed({
  events,
  emptyLabel = "No activity yet.",
  className,
}: {
  events: JobEvent[];
  emptyLabel?: string;
  className?: string;
}) {
  if (events.length === 0) {
    return <p className={cn("text-[13px] text-muted", className)}>{emptyLabel}</p>;
  }

  return (
    <ol className={cn("space-y-0", className)}>
      {events.map((event, index) => {
        const { Icon, className: iconClass } = eventIcon(event.type);
        return (
          <li key={event.id} className="relative flex gap-3 pb-4 last:pb-0">
            {index < events.length - 1 ? (
              <span className="absolute left-[13px] top-7 h-[calc(100%-16px)] w-px bg-line" />
            ) : null}
            <span
              className={cn(
                "relative z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
                iconClass,
              )}
            >
              <Icon className="size-3.5" />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-[12.5px] font-medium text-ink-soft">
                  {titleCase(event.type)}
                </p>
                <time className="shrink-0 text-[10.5px] text-faint">
                  {formatDateTime(event.created_at)}
                </time>
              </div>
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">
                {event.message}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
