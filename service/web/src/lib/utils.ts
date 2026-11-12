import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Job, JobStatus, PrepStatus, StageStatus } from "./types";

/** Mol* built-in structure formats, keyed by upload suffix. */
export type ViewerStructureFormat =
  | "pdb"
  | "mmcif"
  | "gro"
  | "xyz"
  | "mol"
  | "sdf"
  | "mol2";

const VIEWER_FORMATS_BY_SUFFIX: Record<string, ViewerStructureFormat> = {
  pdb: "pdb",
  ent: "pdb",
  cif: "mmcif",
  mmcif: "mmcif",
  gro: "gro",
  xyz: "xyz",
  mol: "mol",
  sdf: "sdf",
  sd: "sdf",
  mol2: "mol2",
};

/** Map an uploaded structure filename to the viewer format id, if renderable. */
export function structureFormat(fileName: string): ViewerStructureFormat | null {
  const suffix = fileName.includes(".")
    ? fileName.split(".").pop()!.toLowerCase()
    : "";
  return VIEWER_FORMATS_BY_SUFFIX[suffix] ?? null;
}

/**
 * Map a response content type to the viewer format id.
 *
 * A derived preview is always served as PDB whatever the source format was,
 * so the viewer asks the server instead of trusting the file name.
 */
export function structureFormatFromContentType(
  contentType: string,
): ViewerStructureFormat | null {
  const type = contentType.toLowerCase();
  if (type.includes("x-pdb")) return "pdb";
  if (type.includes("x-cif")) return "mmcif";
  return null;
}

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  return `${value >= 100 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });
  if (abs < 60) return formatter.format(seconds, "second");
  if (abs < 3600) return formatter.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
  return formatter.format(Math.round(seconds / 86400), "day");
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "—";
  }
  if (seconds < 1) return "< 1s";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = Math.round(seconds % 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${rest}s`;
  return `${rest}s`;
}

export function elapsedSeconds(
  startedAt: string | null | undefined,
  completedAt?: string | null,
): number | null {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function humanizeStage(name: string): string {
  if (name === "minimization") return "Energy minimization";
  if (name === "production") return "Production";
  const match = name.match(/^equil-(\d+)$/);
  if (match) return `Equilibration ${Number(match[1])}`;
  return titleCase(name);
}

export const ACTIVE_STATUSES: JobStatus[] = [
  "queued",
  "claimed",
  "running",
  "canceling",
];

export function isActive(status: JobStatus | undefined): boolean {
  return status ? ACTIVE_STATUSES.includes(status) : false;
}

/**
 * Prep jobs use their own status vocabulary.  A claimed job is already
 * picked up by a worker, so it is still active even though it is not
 * "running" yet.
 */
export const ACTIVE_PREP_STATUSES: PrepStatus[] = [
  "pending",
  "queued",
  "claimed",
  "running",
];

export function isPrepActive(status: PrepStatus | undefined): boolean {
  return status ? ACTIVE_PREP_STATUSES.includes(status) : false;
}

export function isTerminal(
  status: JobStatus | PrepStatus | undefined,
): boolean {
  return (
    status === "completed" || status === "failed" || status === "canceled"
  );
}

export function jobPercent(job: Job | undefined): number {
  if (!job) return 0;
  const percent = job.progress?.percent;
  if (typeof percent === "number" && Number.isFinite(percent)) {
    return Math.max(0, Math.min(100, percent));
  }
  if (job.status === "completed") return 100;
  return 0;
}

export function statusLabel(status: JobStatus | StageStatus | string): string {
  switch (status) {
    case "claimed":
      return "Starting";
    case "canceling":
      return "Stopping";
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    case "canceled":
      return "Canceled";
    case "skipped":
      return "Skipped";
    case "pending":
      return "Pending";
    default:
      return titleCase(status);
  }
}

export function stageProgress(completed: number, target: number): number {
  if (!target) return 0;
  return Math.max(0, Math.min(100, (completed / target) * 100));
}

export function formatSimulationLength(steps: number, timestepPs = 0.002): string {
  const ns = (steps * timestepPs) / 1000;
  if (ns >= 1000) return `${(ns / 1000).toFixed(1)} µs`;
  if (ns >= 1) return `${ns.toFixed(ns >= 10 ? 0 : 1)} ns`;
  return `${(ns * 1000).toFixed(0)} ps`;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
