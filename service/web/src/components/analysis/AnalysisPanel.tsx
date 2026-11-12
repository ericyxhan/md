import { Suspense, useMemo } from "react";
import { Plus, RotateCcw, Thermometer, Droplets, Activity, Package } from "lucide-react";
import {
  useJobSeries,
  useJobViews,
} from "../../lib/queries";
import { formatCompact } from "../../lib/utils";
import { Card, CardBody, CardHeader } from "../ui/Card";
import { Button } from "../ui/Button";
import { EmptyState, Spinner } from "../ui/EmptyState";
import { ChartCard } from "./ChartCard";
import { SeriesChart } from "./SeriesChart";
import { LazyTrajectoryPlayer } from "../viewer/lazy";

type AnalysisPanelProps = {
  jobId: string;
};

/**
 * Analysis tab for a completed (or in-progress) job. Renders:
 * 1. Composition metrics from the view manifest (prepared view).
 * 2. Time-series charts from the analysis series (temperature, density,
 *    potential/kinetic energy vs. step).
 * 3. Trajectory playback (view.pdb + view.dcd) when a trajectory view exists.
 */
export function AnalysisPanel({ jobId }: AnalysisPanelProps) {
  const views = useJobViews(jobId, true, false);
  const series = useJobSeries(jobId, true);

  if (views.isLoading || series.isLoading) {
    return (
      <div className="flex h-[400px] items-center justify-center text-[12px] text-muted">
        <Spinner className="size-4" /> Loading analysis
      </div>
    );
  }

  if (views.isError || series.isError) {
    return (
      <EmptyState
        icon={<RotateCcw className="size-5 text-rose-600" />}
        title="Analysis unavailable"
        description={
          (() => {
            const err = views.error ?? series.error;
            return err instanceof Error ? err.message : "The analysis data could not be loaded.";
          })()
        }
      />
    );
  }

  const prepared = views.data?.items.find((view) => view.group === "prepared");
  const stageView = views.data?.items.find(
    (view) => view.group !== "prepared"
  );
  const manifest = prepared?.manifest_data;

  return (
    <div className="px-5 py-4 space-y-4">
      {/* Composition metrics card */}
      {manifest ? (
        <Card className="overflow-hidden">
          <CardHeader
            title="System composition"
            description="Solute-focused view of the built system (solvent and ions removed)."
          />
          <CardBody className="px-5 pb-4">
            <div className="grid grid-cols-2 gap-4 text-[11px]">
              <MetricRow
                label="Solute atoms"
                value={formatCompact(manifest.view_atoms)}
                icon={<Package className="size-4 text-brand-600" />}
              />
              <MetricRow
                label="System atoms"
                value={formatCompact(manifest.source_atoms)}
                icon={<Package className="size-4 text-muted" />}
              />
              <MetricRow
                label="Waters removed"
                value={formatCompact(manifest.water_residues)}
                icon={<Droplets className="size-4 text-brand-600" />}
              />
              <MetricRow
                label="Ions"
                value={formatCompact(manifest.ion_atoms)}
                icon={<Plus className="size-4 text-brand-600" />}
              />
              {manifest.box && (
                <MetricRow
                  label="Box (a × b × c)"
                  value={`${manifest.box.a.toFixed(0)} × ${manifest.box.b.toFixed(0)} × ${manifest.box.c.toFixed(0)} Å`}
                  icon={<Activity className="size-4 text-brand-600" />}
                />
              )}
              {manifest.truncated && (
                <div className="col-span-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] leading-relaxed text-amber-900">
                  <span className="mr-1">⚠</span>
                  The solute exceeded the view budget of{" "}
                  {formatCompact(25_000)} atoms; later atoms are hidden from
                  this view.
                </div>
              )}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {/* Time-series charts */}
      {series.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <ChartCard
            title="Temperature"
            description="System temperature vs. simulation step (K)."
          >
            <SeriesChart
              points={series.data.points}
              column="temperature_k"
              unit="K"
            />
          </ChartCard>
          <ChartCard
            title="Density"
            description="Box density vs. simulation step (g/mL)."
          >
            <SeriesChart points={series.data.points} column="density_g_ml" unit="g/mL" />
          </ChartCard>
          <ChartCard
            title="Potential Energy"
            description="Potential energy vs. simulation step (kJ/mol)."
          >
            <SeriesChart
              points={series.data.points}
              column="potential_energy_kj_mol"
            />
          </ChartCard>
          <ChartCard
            title="Box Volume"
            description="Simulation box volume vs. simulation step (nm³)."
          >
            <SeriesChart points={series.data.points} column="volume_nm3" unit="nm³" />
          </ChartCard>
        </div>
      ) : (
        <EmptyState
          icon={<Thermometer className="size-5 text-faint" />}
          title="No time-series data"
          description={
            "This job has no analysis series yet. The worker generates "
            + "series.json from simulation.log when a stage completes."
          }
        />
      )}

      {/* Trajectory player */}
      {stageView && stageView.structure && stageView.trajectory ? (
        <ChartCard
          title="Trajectory"
          description={
            `Mol* playback of ${stageView.trajectory.name} (${formatCompact(
              stageView.trajectory.size_bytes
            )})`
          }
        >
          <Suspense
            fallback={
              <div className="flex h-[320px] items-center justify-center gap-2 text-[12.5px] text-muted">
                <Spinner /> Loading player
              </div>
            }
          >
            <LazyTrajectoryPlayer
              pdbUrl={stageView.structure.url}
              dcdUrl={stageView.trajectory.url}
              label={stageView.trajectory.name}
            />
          </Suspense>
        </ChartCard>
      ) : null}
    </div>
  );
}

function MetricRow({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="shrink-0 text-muted">{icon}</span>
      <div>
        <p className="text-[10px] uppercase tracking-[0.08em] text-faint">
          {label}
        </p>
        <p className="text-[12px] font-medium text-ink-soft">{value}</p>
      </div>
    </div>
  );
}
