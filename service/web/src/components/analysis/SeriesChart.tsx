import { useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { SeriesPoint } from "../../lib/types";

/**
 * Renders a single numeric series from a `SeriesOut.points` array as a line
 * chart. The *column* argument selects which schema field to plot (e.g.
 * "temperature_k", "potential_energy_kj_mol", "density_g_ml").
 */
export interface SeriesChartProps {
  points: SeriesPoint[];
  column: keyof SeriesPoint;
  unit?: string;
  height?: number;
}

export function SeriesChart({
  points,
  column,
  unit,
  height = 240,
}: SeriesChartProps) {
  const data = useMemo(
    () =>
      points
        .filter((p) => p[column] != null)
        .map((p) => ({
          step: p.step,
          time_ps: p.time_ps ?? 0,
          value: p[column] ?? 0,
        })),
    [points, column]
  );

  if (data.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-[12px] text-muted">
        No data for column "{String(column)}".
      </div>
    );
  }

  const columnLabel = String(column)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace("Kj Mol", "kJ/mol")
    .replace("Nm3", "nm³")
    .replace("G Ml", "g/mL")
    .replace("Ns Day", "ns/day")
    .replace("Elapsed S", "elapsed (s)")
    .replace("Time Ps", "time (ps)");

  return (
    <div className={`h-[${height}px]`}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="time_ps" label={{ value: "Time (ps)", position: "insideBottomRight", offset: -5 }} />
          <YAxis label={{ value: unit ?? columnLabel, angle: -90, position: "insideLeft" }} />
          <Tooltip
            labelFormatter={(label) => `${Number(label ?? 0).toFixed(1)} ps`}
            formatter={(value) => `${Number(value ?? 0).toFixed(2)} ${unit ?? ""}`}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#17a394"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
