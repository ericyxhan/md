import { cn } from "../../lib/utils";

export function ProgressBar({
  value,
  className,
  tone = "brand",
  animated = false,
}: {
  value: number;
  className?: string;
  tone?: "brand" | "blue" | "green" | "rose" | "amber";
  animated?: boolean;
}) {
  const tones = {
    brand: "bg-brand-500",
    blue: "bg-sky-500",
    green: "bg-emerald-500",
    rose: "bg-rose-500",
    amber: "bg-amber-500",
  };
  return (
    <div
      className={cn("progress-track", className)}
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          "progress-fill",
          tones[tone],
          animated && "animate-soft-pulse",
        )}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function ProgressRing({
  value,
  size = 64,
  stroke = 6,
  label,
  tone = "brand",
}: {
  value: number;
  size?: number;
  stroke?: number;
  label?: string;
  tone?: "brand" | "green" | "rose" | "blue";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;
  const colors = {
    brand: "stroke-brand-500",
    green: "stroke-emerald-500",
    rose: "stroke-rose-500",
    blue: "stroke-sky-500",
  };
  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className="stroke-line"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn(colors[tone], "transition-[stroke-dashoffset] duration-700")}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[12px] font-semibold tabular-nums text-ink">
        {label ?? `${Math.round(clamped)}%`}
      </span>
    </div>
  );
}
