import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleSlash,
  Clock3,
  Layers,
  Play,
  RefreshCw,
  Sparkles,
  Timer,
} from "lucide-react";
import type { EventWithJobOut } from "../../lib/types";
import { cn, formatRelative, titleCase } from "../../lib/utils";
import { StatusBadge } from "../ui/Badge";

/**
 * Map an event type to an icon and tone.  The tone encodes how much the user
 * should care: failures are loud, routine progress is quiet.
 */
function eventVisual(type: string): {
  Icon: typeof Activity;
  className: string;
  attention: boolean;
} {
  switch (type) {
    case "failed":
    case "error":
      return { Icon: AlertCircle, className: "text-rose-600 bg-rose-50", attention: true };
    case "completed":
      return {
        Icon: CheckCircle2,
        className: "text-emerald-600 bg-emerald-50",
        attention: true,
      };
    case "canceled":
    case "cancel_requested":
      return { Icon: CircleSlash, className: "text-amber-600 bg-amber-50", attention: false };
    case "stage":
      return { Icon: Layers, className: "text-sky-600 bg-sky-50", attention: false };
    case "phase_changed":
      return { Icon: Timer, className: "text-violet-600 bg-violet-50", attention: false };
    case "running":
    case "claimed":
      return { Icon: Play, className: "text-brand-600 bg-brand-50", attention: false };
    case "queued":
      return { Icon: Clock3, className: "text-amber-600 bg-amber-50", attention: false };
    case "retried":
      return { Icon: RefreshCw, className: "text-brand-600 bg-brand-50", attention: false };
    case "created":
      return { Icon: Sparkles, className: "text-slate-500 bg-slate-100", attention: false };
    default:
      return { Icon: Sparkles, className: "text-slate-500 bg-slate-100", attention: false };
  }
}

/**
 * Where an event points.  System-preparation jobs live on their own pages,
 * MD simulations on the job detail page.
 */
function eventHref(event: EventWithJobOut): string {
  if (event.source === "prep") {
    const base =
      event.prep_type === "membrane_embed" ? "/prep/membrane" : "/prep/system-prep";
    return `${base}/${event.job_id}`;
  }
  return `/jobs/${event.job_id}`;
}

/**
 * A single account-wide notification row: what happened, to which job, and
 * when.  Clicking the row opens the job that produced the event.
 */
function NotificationRow({ event }: { event: EventWithJobOut }) {
  const navigate = useNavigate();
  const { Icon, className, attention } = eventVisual(event.type);
  const href = eventHref(event);

  return (
    <li>
      <button
        type="button"
        onClick={() => navigate(href)}
        className="group flex w-full items-start gap-3 px-5 py-3 text-left transition hover:bg-surface-muted"
      >
        <span
          className={cn(
            "relative z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
            className,
          )}
        >
          <Icon className="size-3.5" />
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span
              className={cn(
                "truncate text-[12.5px] font-medium",
                attention ? "text-ink" : "text-ink-soft",
              )}
            >
              {event.message}
            </span>
            <time
              className="shrink-0 text-[10.5px] text-faint"
              title={event.created_at}
            >
              {formatRelative(event.created_at)}
            </time>
          </span>

          <span className="mt-1 flex items-center gap-2">
            <span className="truncate text-[11px] text-muted group-hover:text-brand-700">
              {event.job_name}
            </span>
            <StatusBadge
              status={event.job_status}
              className="shrink-0 scale-90 origin-left"
            />
            <span className="shrink-0 text-[10px] uppercase tracking-wide text-faint">
              {titleCase(event.type)}
            </span>
          </span>
        </span>
      </button>
    </li>
  );
}

export function NotificationFeed({
  events,
  emptyLabel = "Nothing has happened yet.",
  className,
}: {
  events: EventWithJobOut[];
  emptyLabel?: string;
  className?: string;
}) {
  if (events.length === 0) {
    return (
      <p className={cn("px-5 py-6 text-[13px] text-muted", className)}>
        {emptyLabel}
      </p>
    );
  }

  return (
    <ol className={cn("divide-y divide-line", className)}>
      {events.map((event) => (
        <NotificationRow key={event.id} event={event} />
      ))}
    </ol>
  );
}
