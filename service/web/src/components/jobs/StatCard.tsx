import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export function StatCard({
  label,
  value,
  detail,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: ReactNode;
  tone?: "neutral" | "brand" | "blue" | "green" | "rose" | "amber";
}) {
  const tones = {
    neutral: "bg-ink/[0.045] text-ink-soft",
    brand: "bg-brand-50 text-brand-700",
    blue: "bg-sky-50 text-sky-700",
    green: "bg-emerald-50 text-emerald-700",
    rose: "bg-rose-50 text-rose-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12px] font-medium text-muted">{label}</p>
        {icon ? (
          <span
            className={cn(
              "flex size-7 items-center justify-center rounded-lg",
              tones[tone],
            )}
          >
            {icon}
          </span>
        ) : null}
      </div>
      <p className="mt-2.5 text-[26px] font-semibold leading-none tracking-[-0.03em] text-ink tabular-nums">
        {value}
      </p>
      {detail ? (
        <p className="mt-2 text-[11.5px] leading-relaxed text-muted">
          {detail}
        </p>
      ) : null}
    </div>
  );
}
