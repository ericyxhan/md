import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { jobStreamUrl } from "./api";
import { queryKeys } from "./queries";
import type { Job, JobEvent } from "./types";

interface ProgressSnapshot {
  id: string;
  status: Job["status"];
  phase?: string | null;
  current_stage?: string | null;
  attempt?: number;
  step?: number | null;
  total_steps?: number | null;
  percent?: number | null;
  progress_updated_at?: string | null;
  updated_at?: string | null;
  error?: Job["error"];
}

/**
 * Subscribe to a job's server-sent event stream.
 *
 * Progress frames patch the cached job immediately, so the UI moves without a
 * refetch.  Persisted events are appended to a local list; the REST event list
 * remains the initial history.  If the stream cannot reconnect, the normal
 * polling queries keep the page correct.
 */
export function useJobStream(jobId: string | undefined) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [liveEvents, setLiveEvents] = useState<JobEvent[]>([]);
  const eventIds = useRef<Set<number>>(new Set());
  const lastEventId = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!jobId) return;

    let source: EventSource | null = null;
    let disposed = false;
    let failures = 0;

    const recordEvent = (event: JobEvent) => {
      if (typeof event.id === "number") {
        if (eventIds.current.has(event.id)) return;
        eventIds.current.add(event.id);
        lastEventId.current = Math.max(
          lastEventId.current ?? 0,
          event.id,
        );
      }
      setLiveEvents((previous) => [...previous, event]);
    };

    const connect = () => {
      if (disposed) return;
      source = new EventSource(jobStreamUrl(jobId, lastEventId.current));

      source.onopen = () => {
        failures = 0;
        setConnected(true);
      };

      source.addEventListener("job", (message) => {
        try {
          recordEvent(JSON.parse((message as MessageEvent).data) as JobEvent);
        } catch {
          // Ignore malformed frames; the polling path remains authoritative.
        }
        queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId) });
      });

      source.addEventListener("progress", (message) => {
        try {
          const snapshot = JSON.parse(
            (message as MessageEvent).data,
          ) as ProgressSnapshot;
          queryClient.setQueryData<Job>(
            queryKeys.job(jobId),
            (previous) => {
              if (!previous) return previous;
              return {
                ...previous,
                status: snapshot.status,
                phase: snapshot.phase ?? previous.phase,
                current_stage:
                  snapshot.current_stage ?? previous.current_stage,
                attempt: snapshot.attempt ?? previous.attempt,
                progress: {
                  step: snapshot.step ?? null,
                  total_steps: snapshot.total_steps ?? null,
                  percent: snapshot.percent ?? null,
                  updated_at: snapshot.progress_updated_at ?? null,
                },
                error: snapshot.error ?? previous.error,
                updated_at: snapshot.updated_at ?? previous.updated_at,
              };
            },
          );
        } catch {
          // Ignore malformed frames.
        }
      });

      source.addEventListener("end", () => {
        setConnected(false);
        source?.close();
        queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.events(jobId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.artifacts(jobId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.logs(jobId) });
      });

      source.onerror = () => {
        setConnected(false);
        failures += 1;
        // EventSource retries on its own. After repeated failures (for example
        // an expired session), stop and let React Query polling take over.
        if (failures >= 5) {
          source?.close();
        }
      };
    };

    connect();

    return () => {
      disposed = true;
      source?.close();
    };
  }, [jobId, queryClient]);

  return { connected, liveEvents };
}
