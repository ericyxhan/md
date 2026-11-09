import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Cpu,
  FlaskConical,
  ListChecks,
  Plus,
  Rocket,
} from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { useCapabilities, useJobs } from "../lib/queries";
import { formatCompact, formatRelative, isActive } from "../lib/utils";
import { PageHeader } from "../components/layout/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState, PageLoader } from "../components/ui/EmptyState";
import { StatCard } from "../components/jobs/StatCard";
import { ActiveJobCard, JobRow } from "../components/jobs/JobCards";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function SkeletonCards() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="card animate-pulse p-4">
          <div className="h-3 w-20 rounded bg-line" />
          <div className="mt-3 h-7 w-12 rounded bg-line" />
          <div className="mt-3 h-2.5 w-28 rounded bg-line" />
        </div>
      ))}
    </div>
  );
}

export function DashboardPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const jobs = useJobs(undefined, 50);
  const capabilities = useCapabilities();

  if (jobs.isLoading) {
    return (
      <div>
        <PageHeader title="Overview" description="Loading your workspace…" />
        <div className="mt-6">
          <SkeletonCards />
        </div>
      </div>
    );
  }

  if (jobs.isError || !jobs.data) {
    return (
      <div className="card mt-6">
        <EmptyState
          icon={<AlertTriangle className="size-5" />}
          title="Could not load simulations"
          description={
            jobs.error instanceof Error
              ? jobs.error.message
              : "The jobs endpoint is unavailable."
          }
          action={<Button onClick={() => void jobs.refetch()}>Try again</Button>}
        />
      </div>
    );
  }

  const items = jobs.data.items;
  const running = items.filter(
    (job) => job.status === "running" || job.status === "claimed",
  );
  const queued = items.filter((job) => job.status === "queued");
  const completed = items.filter((job) => job.status === "completed");
  const failed = items.filter((job) => job.status === "failed");
  const active = [...running, ...queued].slice(0, 3);
  const recent = items.slice(0, 8);

  const today = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());

  return (
    <div>
      <PageHeader
        eyebrow={today}
        title={`${greeting()}, ${session?.owner === "local" ? "lab" : session?.owner ?? "lab"}`}
        description="Launch simulations, follow live progress, and collect finished trajectories from one place."
        actions={
          <Button
            variant="primary"
            onClick={() => navigate("/new")}
            leadingIcon={<Plus className="size-4" />}
          >
            New simulation
          </Button>
        }
      />

      {capabilities.data ? (
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-line bg-surface px-4 py-2.5 text-[11.5px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
            </span>
            Service online
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Cpu className="size-3.5" />
            {capabilities.data.simulation_platform} platform
          </span>
          <span className="inline-flex items-center gap-1.5">
            <ListChecks className="size-3.5" />
            Queue limit {capabilities.data.limits.max_queued_jobs_per_owner}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <FlaskConical className="size-3.5" />
            {capabilities.data.ligand_forcefield}
          </span>
          <Link
            to="/jobs"
            className="ml-auto inline-flex items-center gap-1 font-medium text-brand-700 hover:text-brand-800"
          >
            All simulations
            <ArrowRight className="size-3" />
          </Link>
        </div>
      ) : null}

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Running now"
          value={running.length}
          detail={
            running.length
              ? "GPU work in progress"
              : "No simulation is executing"
          }
          icon={<Activity className="size-3.5" />}
          tone="blue"
        />
        <StatCard
          label="In the queue"
          value={queued.length}
          detail={
            queued.length
              ? `Next up: ${queued[0]?.name ?? "—"}`
              : "The worker is free"
          }
          icon={<Clock3 className="size-3.5" />}
          tone="amber"
        />
        <StatCard
          label="Completed"
          value={completed.length}
          detail="Finished in the loaded window"
          icon={<CheckCircle2 className="size-3.5" />}
          tone="green"
        />
        <StatCard
          label="Needs attention"
          value={failed.length}
          detail={
            failed.length
              ? `Last: ${failed[0]?.name ?? "—"}`
              : "No failed simulations"
          }
          icon={<AlertTriangle className="size-3.5" />}
          tone={failed.length ? "rose" : "neutral"}
        />
      </div>

      {active.length > 0 ? (
        <section className="mt-7">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
                In progress
              </h2>
              <p className="text-[12px] text-muted">
                Progress updates arrive over a live event stream.
              </p>
            </div>
            <Link
              to="/jobs"
              className="text-[12px] font-medium text-brand-700 hover:text-brand-800"
            >
              View all
            </Link>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {active.map((job) => (
              <ActiveJobCard key={job.id} job={job} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="mt-7">
        <Card className="overflow-hidden">
          <CardHeader
            title="Recent simulations"
            description="The latest runs across this workspace."
            action={
              <Link
                to="/jobs"
                className="inline-flex items-center gap-1 text-[12px] font-medium text-brand-700 hover:text-brand-800"
              >
                See all
                <ArrowRight className="size-3" />
              </Link>
            }
          />
          {recent.length === 0 ? (
            <EmptyState
              icon={<Rocket className="size-5" />}
              title="No simulations yet"
              description="Upload a protein–ligand structure and launch your first run. It only takes a few minutes to configure."
              action={
                <Button
                  variant="primary"
                  onClick={() => navigate("/new")}
                  leadingIcon={<Plus className="size-4" />}
                >
                  Start a simulation
                </Button>
              }
            />
          ) : (
            <div className="divide-y divide-line">
              {recent.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </div>
          )}
        </Card>
      </section>

      {items.some((job) => isActive(job.status)) ? (
        <p className="mt-4 text-center text-[11px] text-faint">
          {formatCompact(items.length)} simulations loaded · last refresh{" "}
          {formatRelative(new Date().toISOString())}
        </p>
      ) : null}
    </div>
  );
}
