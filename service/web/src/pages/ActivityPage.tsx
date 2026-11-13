import { useMemo, useState } from "react";
import { Bell, Inbox, X } from "lucide-react";
import { useEventFeed, useJobs, usePrepJobs } from "../lib/queries";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState, Spinner } from "../components/ui/EmptyState";
import { Select } from "../components/ui/Form";
import { NotificationFeed } from "../components/jobs/NotificationFeed";
import type { EventWithJobOut } from "../lib/types";

const EVENT_TYPES: Array<{ value: string; label: string }> = [
  { value: "created", label: "Created" },
  { value: "queued", label: "Queued" },
  { value: "claimed", label: "Claimed" },
  { value: "running", label: "Running" },
  { value: "phase_changed", label: "Phase changed" },
  { value: "stage", label: "Stage" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "retried", label: "Retried" },
  { value: "canceled", label: "Canceled" },
  { value: "cancel_requested", label: "Cancel requested" },
];

function prepLabel(job: { type: string; created_at: string }): string {
  const date = new Date(job.created_at).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
  const kind =
    job.type === "membrane_embed"
      ? "Membrane embedding"
      : job.type === "system_prep"
        ? "System preparation"
        : job.type;
  return `${kind} · ${date}`;
}

/**
 * The account-wide activity history, paged backwards from the newest event.
 *
 * The overview shows a short summary of this feed; this page is where the
 * full history lives.  Filters narrow the feed server-side, and "Load more"
 * pages backwards through it.
 */
export function ActivityPage() {
  const [jobId, setJobId] = useState("");
  const [eventType, setEventType] = useState("");

  const jobs = useJobs(undefined, 50);
  const prepJobs = usePrepJobs();

  const feed = useEventFeed({
    jobId: jobId || null,
    eventType: eventType || null,
    limit: 25,
  });

  const events = useMemo(
    () =>
      feed.data?.pages.flatMap((page: { items: EventWithJobOut[] }) => page.items) ??
      [],
    [feed.data],
  );

  const filtersActive = Boolean(jobId) || Boolean(eventType);

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Activity"
        description="Everything that has happened across your simulations and preparations, newest first."
      />

      <Card className="mt-6 overflow-hidden">
        <CardHeader
          title="All activity"
          description={`${events.length} event${events.length === 1 ? "" : "s"} loaded${filtersActive ? " with filters" : ""}`}
          action={
            filtersActive ? (
              <button
                type="button"
                onClick={() => {
                  setJobId("");
                  setEventType("");
                }}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-muted transition hover:bg-ink/5 hover:text-ink"
              >
                <X className="size-3.5" />
                Clear filters
              </button>
            ) : null
          }
        />

        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3">
          <Select
            aria-label="Filter by job"
            className="w-56 max-w-full"
            value={jobId}
            onChange={(event) => setJobId(event.target.value)}
          >
            <option value="">All jobs</option>
            <optgroup label="Simulations">
              {(jobs.data?.items ?? []).map((job) => (
                <option key={job.id} value={job.id}>
                  {job.name}
                </option>
              ))}
            </optgroup>
            <optgroup label="Preparations">
              {(prepJobs.data ?? []).map((prepJob) => (
                <option key={prepJob.id} value={prepJob.id}>
                  {prepLabel(prepJob)}
                </option>
              ))}
            </optgroup>
          </Select>

          <Select
            aria-label="Filter by event type"
            className="w-44"
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
          >
            <option value="">All event types</option>
            {EVENT_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>

        {feed.isLoading ? (
          <div className="flex items-center justify-center px-5 py-16 text-[12.5px] text-muted">
            <Spinner className="mr-2" />
            Loading activity
          </div>
        ) : feed.isError ? (
          <div className="px-5 py-12 text-center">
            <p className="text-[13px] font-medium text-rose-600">
              {feed.error instanceof Error
                ? feed.error.message
                : "Could not load the activity feed."}
            </p>
            <Button variant="secondary" size="sm" className="mt-3" onClick={() => void feed.refetch()}>
              Try again
            </Button>
          </div>
        ) : events.length === 0 ? (
          <EmptyState
            icon={<Inbox className="size-5" />}
            title={
              filtersActive ? "Nothing matches these filters" : "No activity yet"
            }
            description={
              filtersActive
                ? "Try clearing the filters to see the whole history."
                : "Launch a simulation and its events will appear here."
            }
          />
        ) : (
          <NotificationFeed
            events={events}
            emptyLabel="No matching activity yet."
          />
        )}

        {feed.isError || events.length === 0 ? null : (
          <div className="flex items-center justify-between border-t border-line px-5 py-3">
            <span className="inline-flex items-center gap-1.5 text-[11px] text-faint">
              <Bell className="size-3" />
              Newest first · updates as jobs run
            </span>
            {feed.hasNextPage ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void feed.fetchNextPage()}
                disabled={feed.isFetchingNextPage}
              >
                {feed.isFetchingNextPage ? "Loading…" : "Load more (older)"}
              </Button>
            ) : (
              <span className="text-[11px] font-medium text-faint">
                {"You're all caught up"}
              </span>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
