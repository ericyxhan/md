import { useQuery } from "@tanstack/react-query";
import {
  getArtifacts,
  getCapabilities,
  getJob,
  getJobConfig,
  getJobEvents,
  getJobSpec,
  getLogs,
  getLogTail,
  getPrepJob,
  listPrepJobs,
  listJobs,
} from "./api";
import { isActive } from "./utils";
import type {
  Job,
  JobEvent,
  PrepJobStatus,
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

export function usePrepJob(id: string | undefined) {
  return useQuery({
    queryKey: ["prep", id] as const,
    queryFn: () => getPrepJob(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data as PrepJobStatus | undefined;
      return data &&
        data.status !== "completed" &&
        data.status !== "failed" &&
        data.status !== "canceled"
        ? 3000
        : false;
    },
  });
}

export function usePrepJobs() {
  return useQuery({
    queryKey: ["prep"] as const,
    queryFn: () => listPrepJobs(),
    refetchInterval: (query) => {
      const data = query.state.data as PrepJobStatus[] | undefined;
      const pending = data?.some(
        (job) => job.status === "queued" || job.status === "running"
      );
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
  return useQuery({
    queryKey: queryKeys.logTail(id ?? "", path ?? ""),
    queryFn: () => getLogTail(id as string, path as string, 400),
    enabled: Boolean(id) && Boolean(path) && enabled,
    refetchInterval: 5000,
  });
}

export type { JobEvent };
