import type { ReactNode } from "react";
import { cn, statusLabel } from "../../lib/utils";

type Tone = "neutral" | "brand" | "blue" | "green" | "amber" | "rose" | "violet";

const toneStyles: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-600 ring-slate-200/70",
  brand: "bg-brand-50 text-brand-700 ring-brand-200/70",
  blue: "bg-sky-50 text-sky-700 ring-sky-200/70",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200/70",
  amber: "bg-amber-50 text-amber-700 ring-amber-200/70",
  rose: "bg-rose-50 text-rose-700 ring-rose-200/70",
  violet: "bg-violet-50 text-violet-700 ring-violet-200/70",
};

const dotStyles: Record<Tone, string> = {
  neutral: "bg-slate-400",
  brand: "bg-brand-500",
  blue: "bg-sky-500",
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
  violet: "bg-violet-500",
};

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  pulse = false,
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ring-1 ring-inset",
        toneStyles[tone],
        className,
      )}
    >
      {dot ? (
        <span
          className={cn(
            "size-1.5 rounded-full",
            dotStyles[tone],
            pulse && "animate-soft-pulse",
          )}
        />
      ) : null}
      {children}
    </span>
  );
}

export function statusTone(status: string): Tone {
  switch (status) {
    case "running":
    case "claimed":
      return "blue";
    case "completed":
      return "green";
    case "canceling":
      return "amber";
    case "failed":
      return "rose";
    case "queued":
      return "violet";
    default:
      return "neutral";
  }
}

export function StatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const active = status === "running" || status === "claimed";
  return (
    <Badge
      tone={statusTone(status)}
      dot
      pulse={active || status === "canceling"}
      className={className}
    >
      {statusLabel(status)}
    </Badge>
  );
}
