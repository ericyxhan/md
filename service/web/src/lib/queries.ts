import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getArtifacts,
  getCapabilities,
  getFileInspect,
  getJob,
  getJobConfig,
  getJobEvents,
  getJobSeries,
  getJobSpec,
  getJobViews,
  getLogs,
  getLogTail,
  getPrepJob,
  listPrepJobs,
  listJobs,
  createWorkflow,
  listWorkflows,
  getWorkflow,
  getEvents,
} from "./api";
import { isActive, isTerminal } from "./utils";
import type {
  FileInspect,
  Job,
  JobEvent,
  PrepJobStatus,
  SeriesOut,
} from "./types";

export const queryKeys = {
  session: ["session"] as const,
  capabilities: ["capabilities"] as const,
  jobs: (status?: string) => ["jobs", status ?? "all"] as const,
  job: (id: string) => ["job", id] as const,
  events: (id: string) => ["job", id, "events"] as const,
  artifacts: (id: string) => ["job", id, "artifacts"] as const,
  logs: (id: string) => ["job", id, "logs"] as const,
  logTail: (id: string, path: string) =>
    ["job", id, "logs", path, "tail"] as const,
  spec: (id: string) => ["job", id, "spec"] as const,
  views: (id: string) => ["job", id, "views"] as const,
  series: (id: string) => ["job", id, "series"] as const,
  fileInspect: (id: string) => ["file", id, "inspect"] as const,
  workflows: ["workflows"] as const,
  workflow: (id: string) => ["workflow", id] as const,
  eventFeed: ["event-feed"] as const,
};

export function useCapabilities() {
  return useQuery({
    queryKey: queryKeys.capabilities,
    queryFn: getCapabilities,
    staleTime: 5 * 60_000,
  });
}

export function useJobs(status?: string, limit = 50) {
  return useQuery({
    queryKey: [...queryKeys.jobs(status), limit],
    queryFn: () => listJobs({ status, limit }),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.items.some((job) => isActive(job.status)) ? 4000 : false;
    },
  });
}

export function useJob(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.job(id ?? ""),
    queryFn: () => getJob(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      return isActive(data?.status) ? 4000 : false;
    },
  });
}

export function useJobEvents(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.events(id ?? ""),
    queryFn: () => getJobEvents(id as string, undefined, 200),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useJobSpec(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.spec(id ?? ""),
    queryFn: () => getJobSpec(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

export function useJobConfig(id: string | undefined) {
  return useQuery({
    queryKey: [...queryKeys.job(id ?? ""), "config"] as const,
    queryFn: () => getJobConfig(id as string),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

/**
 * Derived structure views for a job. Views are written when the worker
 * finalizes a run, so while a run is active the query polls until the first
 * views appear; `poll` is off for terminal jobs.
 */
export function useJobViews(
  id: string | undefined,
  enabled = true,
  poll = false,
) {
  return useQuery({
    queryKey: queryKeys.views(id ?? ""),
    queryFn: () => getJobViews(id as string),
    enabled: Boolean(id) && enabled,
    staleTime: 15_000,
    refetchInterval: (query) =>
      poll && !query.state.data?.items.length ? 10_000 : false,
  });
}

export function usePrepJob(id: string | undefined) {
  return useQuery({
    queryKey: ["prep", id] as const,
    queryFn: () => getPrepJob(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data as PrepJobStatus | undefined;
      return data && !isTerminal(data.status) ? 3000 : false;
    },
  });
}

export function usePrepJobs() {
  return useQuery({
    queryKey: ["prep"] as const,
    queryFn: () => listPrepJobs(),
    refetchInterval: (query) => {
      const data = query.state.data as PrepJobStatus[] | undefined;
      // A claimed prep job is already picked up by a worker, so it still
      // needs polling; only terminal jobs stop.
      const pending = data?.some((job) => !isTerminal(job.status));
      return pending ? 3000 : false;
    },
  });
}

export function useArtifacts(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.artifacts(id ?? ""),
    queryFn: () => getArtifacts(id as string),
    enabled: Boolean(id) && enabled,
    staleTime: 15_000,
  });
}

/**
 * Inspect a stored structure file (PDB only). Returns chains, ligands,
 * components, atom count, model count, and bounding box. Useful for populating
 * chain/ligand pickers in the wizard and prep editor.
 */
export function useFileInspect(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.fileInspect(id ?? ""),
    queryFn: () => getFileInspect(id as string),
    enabled: Boolean(id) && enabled,
    staleTime: 5 * 60_000,
  });
}

/**
 * Downsampled time series for a completed stage from ``/analysis/series``.
 * Series are static once a stage completes, so no polling is needed.
 */
export function useJobSeries(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.series(id ?? ""),
    queryFn: () => getJobSeries(id as string),
    enabled: Boolean(id) && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useLogs(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.logs(id ?? ""),
    queryFn: () => getLogs(id as string),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useLogTail(
  id: string | undefined,
  path: string | undefined,
  enabled = true,
) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.logTail(id ?? "", path ?? ""),
    queryFn: () => getLogTail(id as string, path as string, 400),
    enabled: Boolean(id) && Boolean(path) && enabled,
    // A finished job's log does not change, so stop polling for it.
    refetchInterval: () => {
      const job = queryClient.getQueryData<Job>(queryKeys.job(id ?? ""));
      return job && !isTerminal(job.status) ? 5000 : false;
    },
  });
}

export function useWorkflows() {
  return useQuery({
    queryKey: queryKeys.workflows,
    queryFn: () => listWorkflows(),
    staleTime: 10_000,
  });
}

export function useWorkflow(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.workflow(id ?? ""),
    queryFn: () => getWorkflow(id as string),
    enabled: Boolean(id),
  });
}

export function useEvents(limit = 50) {
  return useQuery({
    queryKey: [...queryKeys.eventFeed, limit],
    queryFn: () => getEvents(limit),
    staleTime: 10_000,
  });
}

export type { JobEvent };
