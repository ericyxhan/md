import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Plus,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useJobs } from "../lib/queries";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { TextInput } from "../components/ui/Form";
import { JobRow } from "../components/jobs/JobCards";
import { cn, isActive } from "../lib/utils";

type Filter = "all" | "active" | "completed" | "failed";

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Needs attention" },
];

export function JobsPage() {
  const jobs = useJobs(undefined, 50);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const items = jobs.data?.items ?? [];

  const counts = useMemo(
    () => ({
      all: items.length,
      active: items.filter((job) => isActive(job.status)).length,
      completed: items.filter((job) => job.status === "completed").length,
      failed: items.filter(
        (job) => job.status === "failed" || job.status === "canceled",
      ).length,
    }),
    [items],
  );

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return items.filter((job) => {
      if (filter === "active" && !isActive(job.status)) return false;
      if (filter === "completed" && job.status !== "completed") return false;
      if (
        filter === "failed" &&
        job.status !== "failed" &&
        job.status !== "canceled"
      ) {
        return false;
      }
      if (!term) return true;
      return (
        job.name.toLowerCase().includes(term) ||
        job.id.toLowerCase().includes(term) ||
        (job.current_stage ?? "").toLowerCase().includes(term)
      );
    });
  }, [items, filter, query]);

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Simulations"
        description="Every run in this workspace, newest first. Open a run to follow stages, read logs, and download artifacts."
        actions={
          <Link to="/new">
            <Button variant="primary" leadingIcon={<Plus className="size-4" />}>
              New simulation
            </Button>
          </Link>
        }
      />

      <Card className="mt-6 overflow-hidden">
        <CardHeader
          title="All runs"
          description={`${counts.all} loaded · 50 most recent`}
          action={
            <div className="relative hidden w-56 sm:block">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
              <TextInput
                className="h-8 pl-8 text-[12px]"
                placeholder="Search name, ID, or stage"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search simulations"
              />
            </div>
          }
        />

        <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-5 py-2.5">
          <SlidersHorizontal className="mr-1 size-3.5 text-faint" />
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={cn(
                "rounded-full px-2.5 py-1 text-[11.5px] font-medium transition",
                filter === item.id
                  ? "bg-ink text-white"
                  : "text-muted hover:bg-ink/5 hover:text-ink",
              )}
            >
              {item.label}
              <span
                className={cn(
                  "ml-1.5 tabular-nums",
                  filter === item.id ? "text-white/70" : "text-faint",
                )}
              >
                {counts[item.id]}
              </span>
            </button>
          ))}
        </div>

        <div className="border-b border-line px-5 py-2.5 sm:hidden">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
            <TextInput
              className="h-9 pl-8 text-[12.5px]"
              placeholder="Search simulations"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>

        {jobs.isLoading ? (
          <div className="divide-y divide-line">
            {[0, 1, 2, 3, 4].map((item) => (
              <div key={item} className="animate-pulse px-5 py-4">
                <div className="h-3 w-48 rounded bg-line" />
                <div className="mt-2 h-2.5 w-32 rounded bg-line" />
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            icon={<Activity className="size-5" />}
            title={
              items.length === 0
                ? "No simulations yet"
                : "No runs match this view"
            }
            description={
              items.length === 0
                ? "Launch a molecular dynamics run from a complex file, separate protein and ligands, or a public PDB ID."
                : "Try a different filter or clear the search."
            }
            action={
              items.length === 0 ? (
                <Link to="/new">
                  <Button
                    variant="primary"
                    leadingIcon={<Plus className="size-4" />}
                  >
                    Start a simulation
                  </Button>
                </Link>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setFilter("all");
                    setQuery("");
                  }}
                >
                  Clear filters
                </Button>
              )
            }
          />
        ) : (
          <div className="divide-y divide-line">
            {visible.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </Card>

      {jobs.isError ? (
        <p className="mt-3 text-[12px] text-rose-600">
          {jobs.error instanceof Error
            ? jobs.error.message
            : "Could not refresh simulations."}
        </p>
      ) : null}
    </div>
  );
}
